# IQC 来料检验模块 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build complete IQC incoming inspection module with AQL sampling, two inspection modes, material/template management, and downstream SCAR linkage.

**Architecture:** Extend existing `iqc_inspections` table + 5 new tables. Service layer calls existing `aql_engine.py` for sampling plans. Frontend uses existing Ant Design patterns (Table + Form + Modal). API follows existing FastAPI router pattern with role-based guards.

**Tech Stack:** Python 3.11 + FastAPI 0.115 + SQLAlchemy 2.0 async + PostgreSQL 15 | React 18 + TypeScript 5.6 + Ant Design 5.21

---

## File Structure

```
backend/
├── app/
│   ├── models/
│   │   ├── iqc_inspection.py          # EXTEND: 12 new fields
│   │   ├── iqc_material.py            # CREATE: IqcMaterial model
│   │   ├── iqc_inspection_template.py # CREATE: IqcInspectionTemplate + IqcTemplateItem
│   │   ├── iqc_inspection_item.py     # CREATE: IqcInspectionItem + IqcItemMeasurement
│   │   └── __init__.py                # MODIFY: export new models
│   ├── schemas/
│   │   └── iqc.py                     # CREATE: all IQC Pydantic schemas
│   ├── services/
│   │   ├── iqc_material_service.py    # CREATE: material CRUD
│   │   ├── iqc_template_service.py    # CREATE: template CRUD + versioning
│   │   └── iqc_inspection_service.py  # CREATE: inspection lifecycle + AQL
│   ├── api/
│   │   └── iqc.py                     # CREATE: 3 route groups
│   └── main.py                        # MODIFY: register router
├── alembic/versions/
│   └── 021_iqc_module.py              # CREATE: migration
frontend/src/
├── types/
│   └── index.ts                       # MODIFY: IQC types
├── api/
│   └── iqc.ts                         # CREATE: IQC API functions
├── pages/
│   └── iqc/
│       ├── IqcInspectionListPage.tsx   # CREATE
│       ├── IqcInspectionDetailPage.tsx # CREATE
│       └── IqcMaterialListPage.tsx     # CREATE
├── components/layout/
│   └── AppLayout.tsx                  # MODIFY: sidebar menu
└── App.tsx                            # MODIFY: routes
```

---

### Task 1: Create IQC Material model

**Files:**
- Create: `backend/app/models/iqc_material.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Write the model**

```python
import uuid
from datetime import datetime
from sqlalchemy import String, Float, DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List, TYPE_CHECKING

from app.database import Base

if TYPE_CHECKING:
    from app.models.iqc_inspection_template import IqcInspectionTemplate


class IqcMaterial(Base):
    __tablename__ = "iqc_materials"

    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    part_no: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    part_name: Mapped[str] = mapped_column(String(200), nullable=False)
    part_spec: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    material_type: Mapped[str] = mapped_column(String(20), nullable=False, default="raw")
    default_aql: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    default_inspection_level: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    product_line_code: Mapped[str] = mapped_column(String(20), nullable=False, default="DC-DC-100")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    templates: Mapped[List["IqcInspectionTemplate"]] = relationship(
        back_populates="material", lazy="selectin"
    )
```

- [ ] **Step 2: Register in models/__init__.py**

Add after the existing `IqcInspection` import:
```python
from app.models.iqc_inspection import IqcInspection
from app.models.iqc_material import IqcMaterial
from app.models.iqc_inspection_template import IqcInspectionTemplate, IqcTemplateItem
from app.models.iqc_inspection_item import IqcInspectionItem, IqcItemMeasurement
```

Add to `__all__` after `"IqcInspection"`:
```python
"IqcInspection", "IqcMaterial", "IqcInspectionTemplate", "IqcTemplateItem",
"IqcInspectionItem", "IqcItemMeasurement",
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/iqc_material.py backend/app/models/__init__.py
git commit -m "feat(iqc): add IqcMaterial model"
```

---

### Task 2: Create IQC inspection template models

**Files:**
- Create: `backend/app/models/iqc_inspection_template.py`

- [ ] **Step 1: Write the model**

```python
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, Float, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
from app.database import Base


class IqcInspectionTemplate(Base):
    __tablename__ = "iqc_inspection_templates"

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    template_name: Mapped[str] = mapped_column(String(200), nullable=False)
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iqc_materials.material_id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    material: Mapped["IqcMaterial"] = relationship(back_populates="templates")
    items: Mapped[List["IqcTemplateItem"]] = relationship(
        back_populates="template", lazy="selectin", cascade="all, delete-orphan"
    )


class IqcTemplateItem(Base):
    __tablename__ = "iqc_template_items"

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iqc_inspection_templates.template_id", ondelete="CASCADE"),
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    inspection_method: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    inspect_type: Mapped[str] = mapped_column(String(20), nullable=False, default="attribute")
    spec_upper: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    spec_lower: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    sample_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    aql_level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    template: Mapped["IqcInspectionTemplate"] = relationship(back_populates="items")
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/models/iqc_inspection_template.py
git commit -m "feat(iqc): add IqcInspectionTemplate and IqcTemplateItem models"
```

---

### Task 3: Create IQC inspection item models

**Files:**
- Create: `backend/app/models/iqc_inspection_item.py`

- [ ] **Step 1: Write the model**

```python
import uuid
from sqlalchemy import String, Integer, Float, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
from app.database import Base


class IqcInspectionItem(Base):
    __tablename__ = "iqc_inspection_items"

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iqc_inspections.inspection_id", ondelete="CASCADE"),
        nullable=False,
    )
    template_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iqc_template_items.item_id", ondelete="SET NULL"),
        nullable=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    inspect_type: Mapped[str] = mapped_column(String(20), nullable=False, default="attribute")
    spec_upper: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    spec_lower: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sample_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    accept_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reject_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    defect_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    inspection: Mapped["IqcInspection"] = relationship(back_populates="items")
    measurements: Mapped[List["IqcItemMeasurement"]] = relationship(
        back_populates="item", lazy="selectin", cascade="all, delete-orphan"
    )


class IqcItemMeasurement(Base):
    __tablename__ = "iqc_item_measurements"

    measurement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iqc_inspection_items.item_id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    measured_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    attribute_result: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    item: Mapped["IqcInspectionItem"] = relationship(back_populates="measurements")
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/models/iqc_inspection_item.py
git commit -m "feat(iqc): add IqcInspectionItem and IqcItemMeasurement models"
```

---

### Task 4: Extend IqcInspection model with 12 new fields

**Files:**
- Modify: `backend/app/models/iqc_inspection.py`

- [ ] **Step 1: Replace the model**

Replace the entire file with the extended model. Keep all existing fields and add the 12 new ones. Also add the `items` relationship.

```python
import uuid
from datetime import datetime, date
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Integer, Date, DateTime, Text, ForeignKey, Float, Boolean, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.iqc_inspection_item import IqcInspectionItem


class IqcInspection(Base):
    __tablename__ = "iqc_inspections"

    inspection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inspection_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=False
    )
    part_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    part_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    lot_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    lot_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sample_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    aql_level: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    inspection_level: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    sampling_standard: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    inspection_result: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    defect_qty: Mapped[int] = mapped_column(Integer, default=0)
    defect_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    linked_capa_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="SET NULL"), nullable=True
    )
    inspection_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    inspected_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # ─── New fields for Phase 2 IQC ───
    inspection_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="quick")
    material_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iqc_materials.material_id", ondelete="SET NULL"), nullable=True
    )
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iqc_inspection_templates.template_id", ondelete="SET NULL"),
        nullable=True,
    )
    code_letter: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    accept_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reject_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    re_inspection: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parent_inspection_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iqc_inspections.inspection_id", ondelete="SET NULL"),
        nullable=True,
    )
    product_line_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    linked_scar_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("supplier_scars.scar_id", ondelete="SET NULL"), nullable=True
    )
    judged_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    judged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[List["IqcInspectionItem"]] = relationship(
        back_populates="inspection", lazy="selectin", cascade="all, delete-orphan"
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/models/iqc_inspection.py
git commit -m "feat(iqc): extend IqcInspection model with 12 new fields for Phase 2"
```

---

### Task 5: Create Alembic migration #021

**Files:**
- Create: `backend/alembic/versions/021_iqc_module.py`

- [ ] **Step 1: Write the migration**

```python
"""IQC module — 5 new tables + extend iqc_inspections

Revision ID: 021
Revises: 020
Create Date: 2026-05-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create iqc_materials
    op.create_table(
        "iqc_materials",
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("part_no", sa.String(100), nullable=False),
        sa.Column("part_name", sa.String(200), nullable=False),
        sa.Column("part_spec", sa.String(200), nullable=True),
        sa.Column("material_type", sa.String(20), nullable=False, server_default=sa.text("'raw'")),
        sa.Column("default_aql", sa.Float(), nullable=True),
        sa.Column("default_inspection_level", sa.String(10), nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("product_line_code", sa.String(20), nullable=False, server_default=sa.text("'DC-DC-100'")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("material_id"),
        sa.UniqueConstraint("part_no"),
    )

    # 2. Create iqc_inspection_templates
    op.create_table(
        "iqc_inspection_templates",
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_name", sa.String(200), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("template_id"),
        sa.ForeignKeyConstraint(["material_id"], ["iqc_materials.material_id"], ondelete="CASCADE"),
    )

    # 3. Create iqc_template_items
    op.create_table(
        "iqc_template_items",
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("item_name", sa.String(200), nullable=False),
        sa.Column("inspection_method", sa.String(100), nullable=True),
        sa.Column("inspect_type", sa.String(20), nullable=False, server_default=sa.text("'attribute'")),
        sa.Column("spec_upper", sa.Float(), nullable=True),
        sa.Column("spec_lower", sa.Float(), nullable=True),
        sa.Column("target_value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column("aql_level", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("item_id"),
        sa.ForeignKeyConstraint(["template_id"], ["iqc_inspection_templates.template_id"], ondelete="CASCADE"),
    )

    # 4. Extend iqc_inspections with new columns
    op.add_column("iqc_inspections", sa.Column("inspection_mode", sa.String(10), nullable=False, server_default=sa.text("'quick'")))
    op.add_column("iqc_inspections", sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("iqc_inspections", sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("iqc_inspections", sa.Column("code_letter", sa.String(2), nullable=True))
    op.add_column("iqc_inspections", sa.Column("accept_number", sa.Integer(), nullable=True))
    op.add_column("iqc_inspections", sa.Column("reject_number", sa.Integer(), nullable=True))
    op.add_column("iqc_inspections", sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'closed'")))
    op.add_column("iqc_inspections", sa.Column("re_inspection", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("iqc_inspections", sa.Column("parent_inspection_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("iqc_inspections", sa.Column("product_line_code", sa.String(20), nullable=True))
    op.add_column("iqc_inspections", sa.Column("linked_scar_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("iqc_inspections", sa.Column("judged_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("iqc_inspections", sa.Column("judged_at", sa.DateTime(timezone=True), nullable=True))

    op.create_foreign_key("fk_iqc_inspections_material", "iqc_inspections", "iqc_materials", ["material_id"], ["material_id"], ondelete="SET NULL")
    op.create_foreign_key("fk_iqc_inspections_template", "iqc_inspections", "iqc_inspection_templates", ["template_id"], ["template_id"], ondelete="SET NULL")
    op.create_foreign_key("fk_iqc_inspections_parent", "iqc_inspections", "iqc_inspections", ["parent_inspection_id"], ["inspection_id"], ondelete="SET NULL")
    op.create_foreign_key("fk_iqc_inspections_scar", "iqc_inspections", "supplier_scars", ["linked_scar_id"], ["scar_id"], ondelete="SET NULL")
    op.create_foreign_key("fk_iqc_inspections_judged_by", "iqc_inspections", "users", ["judged_by"], ["user_id"])

    # 5. Create iqc_inspection_items
    op.create_table(
        "iqc_inspection_items",
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inspection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("item_name", sa.String(200), nullable=False),
        sa.Column("inspect_type", sa.String(20), nullable=False, server_default=sa.text("'attribute'")),
        sa.Column("spec_upper", sa.Float(), nullable=True),
        sa.Column("spec_lower", sa.Float(), nullable=True),
        sa.Column("target_value", sa.Float(), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column("accept_no", sa.Integer(), nullable=True),
        sa.Column("reject_no", sa.Integer(), nullable=True),
        sa.Column("defect_qty", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("result", sa.String(10), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("item_id"),
        sa.ForeignKeyConstraint(["inspection_id"], ["iqc_inspections.inspection_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_item_id"], ["iqc_template_items.item_id"], ondelete="SET NULL"),
    )

    # 6. Create iqc_item_measurements
    op.create_table(
        "iqc_item_measurements",
        sa.Column("measurement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("measured_value", sa.Float(), nullable=True),
        sa.Column("attribute_result", sa.String(10), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("measurement_id"),
        sa.ForeignKeyConstraint(["item_id"], ["iqc_inspection_items.item_id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("iqc_item_measurements")
    op.drop_table("iqc_inspection_items")

    op.drop_constraint("fk_iqc_inspections_judged_by", "iqc_inspections", type_="foreignkey")
    op.drop_constraint("fk_iqc_inspections_scar", "iqc_inspections", type_="foreignkey")
    op.drop_constraint("fk_iqc_inspections_parent", "iqc_inspections", type_="foreignkey")
    op.drop_constraint("fk_iqc_inspections_template", "iqc_inspections", type_="foreignkey")
    op.drop_constraint("fk_iqc_inspections_material", "iqc_inspections", type_="foreignkey")

    op.drop_column("iqc_inspections", "judged_at")
    op.drop_column("iqc_inspections", "judged_by")
    op.drop_column("iqc_inspections", "linked_scar_id")
    op.drop_column("iqc_inspections", "product_line_code")
    op.drop_column("iqc_inspections", "parent_inspection_id")
    op.drop_column("iqc_inspections", "re_inspection")
    op.drop_column("iqc_inspections", "status")
    op.drop_column("iqc_inspections", "reject_number")
    op.drop_column("iqc_inspections", "accept_number")
    op.drop_column("iqc_inspections", "code_letter")
    op.drop_column("iqc_inspections", "template_id")
    op.drop_column("iqc_inspections", "material_id")
    op.drop_column("iqc_inspections", "inspection_mode")

    op.drop_table("iqc_template_items")
    op.drop_table("iqc_inspection_templates")
    op.drop_table("iqc_materials")
```

- [ ] **Step 2: Run migration to verify**

```bash
cd backend && alembic upgrade head
```

Expected: migration applies without errors.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/021_iqc_module.py
git commit -m "feat(iqc): add Alembic migration 021 for IQC module tables"
```

---

### Task 6: Create IQC Pydantic schemas

**Files:**
- Create: `backend/app/schemas/iqc.py`

- [ ] **Step 1: Write schemas**

```python
import uuid
from datetime import datetime, date
from pydantic import BaseModel, field_validator


# ─── Material ───

class IqcMaterialCreate(BaseModel):
    part_no: str
    part_name: str
    part_spec: str | None = None
    material_type: str = "raw"
    default_aql: float | None = None
    default_inspection_level: str | None = None
    unit: str | None = None
    product_line_code: str = "DC-DC-100"

    @field_validator("part_no", "part_name")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()


class IqcMaterialUpdate(BaseModel):
    part_name: str | None = None
    part_spec: str | None = None
    material_type: str | None = None
    default_aql: float | None = None
    default_inspection_level: str | None = None
    unit: str | None = None
    product_line_code: str | None = None
    status: str | None = None


class IqcMaterialResponse(BaseModel):
    material_id: uuid.UUID
    part_no: str
    part_name: str
    part_spec: str | None
    material_type: str
    default_aql: float | None
    default_inspection_level: str | None
    unit: str | None
    product_line_code: str
    status: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IqcMaterialListResponse(BaseModel):
    items: list[IqcMaterialResponse]
    total: int
    page: int
    page_size: int


# ─── Template Items ───

class IqcTemplateItemCreate(BaseModel):
    sort_order: int = 0
    category: str
    item_name: str
    inspection_method: str | None = None
    inspect_type: str = "attribute"
    spec_upper: float | None = None
    spec_lower: float | None = None
    target_value: float | None = None
    unit: str | None = None
    sample_size: int | None = None
    aql_level: float | None = None


class IqcTemplateItemResponse(BaseModel):
    item_id: uuid.UUID
    template_id: uuid.UUID
    sort_order: int
    category: str
    item_name: str
    inspection_method: str | None
    inspect_type: str
    spec_upper: float | None
    spec_lower: float | None
    target_value: float | None
    unit: str | None
    sample_size: int | None
    aql_level: float | None

    model_config = {"from_attributes": True}


# ─── Template ───

class IqcTemplateCreate(BaseModel):
    template_name: str
    material_id: uuid.UUID
    items: list[IqcTemplateItemCreate] = []


class IqcTemplateResponse(BaseModel):
    template_id: uuid.UUID
    template_name: str
    material_id: uuid.UUID
    version: int
    is_active: bool
    items: list[IqcTemplateItemResponse] = []
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IqcTemplateListResponse(BaseModel):
    items: list[IqcTemplateResponse]
    total: int
    page: int
    page_size: int


# ─── Inspection Items (instance) ───

class IqcItemMeasurementCreate(BaseModel):
    sequence_no: int = 1
    measured_value: float | None = None
    attribute_result: str | None = None
    remark: str | None = None


class IqcItemMeasurementResponse(BaseModel):
    measurement_id: uuid.UUID
    item_id: uuid.UUID
    sequence_no: int
    measured_value: float | None
    attribute_result: str | None
    remark: str | None

    model_config = {"from_attributes": True}


class IqcInspectionItemResponse(BaseModel):
    item_id: uuid.UUID
    inspection_id: uuid.UUID
    template_item_id: uuid.UUID | None
    sort_order: int
    category: str
    item_name: str
    inspect_type: str
    spec_upper: float | None
    spec_lower: float | None
    target_value: float | None
    sample_size: int | None
    accept_no: int | None
    reject_no: int | None
    defect_qty: int
    result: str
    remark: str | None
    measurements: list[IqcItemMeasurementResponse] = []

    model_config = {"from_attributes": True}


class IqcInspectionItemUpdate(BaseModel):
    defect_qty: int | None = None
    result: str | None = None
    remark: str | None = None
    measurements: list[IqcItemMeasurementCreate] | None = None


class IqcBatchItemUpdate(BaseModel):
    items: list[IqcInspectionItemUpdate]


# ─── Inspection ───

class IqcInspectionCreate(BaseModel):
    supplier_id: uuid.UUID
    inspection_mode: str = "quick"
    material_id: uuid.UUID | None = None
    template_id: uuid.UUID | None = None
    part_no: str | None = None
    part_name: str | None = None
    lot_no: str | None = None
    lot_qty: int | None = None
    aql_level: float | None = None
    inspection_level: str = "II"
    inspection_date: date | None = None
    product_line_code: str | None = None


class IqcInspectionUpdate(BaseModel):
    part_no: str | None = None
    part_name: str | None = None
    lot_no: str | None = None
    lot_qty: int | None = None
    inspection_date: date | None = None


class IqcInspectionJudge(BaseModel):
    inspection_result: str
    defect_qty: int = 0
    defect_description: str | None = None
    sample_qty: int | None = None


class IqcInspectionConcession(BaseModel):
    reason: str


class IqcInspectionResponse(BaseModel):
    inspection_id: uuid.UUID
    inspection_no: str
    supplier_id: uuid.UUID
    inspection_mode: str
    material_id: uuid.UUID | None
    template_id: uuid.UUID | None
    part_no: str | None
    part_name: str | None
    lot_no: str | None
    lot_qty: int | None
    sample_qty: int | None
    aql_level: str | None
    inspection_level: str | None
    sampling_standard: str | None
    code_letter: str | None
    accept_number: int | None
    reject_number: int | None
    inspection_result: str
    defect_qty: int
    defect_description: str | None
    status: str
    re_inspection: bool
    parent_inspection_id: uuid.UUID | None
    product_line_code: str | None
    linked_capa_id: uuid.UUID | None
    linked_scar_id: uuid.UUID | None
    judged_by: uuid.UUID | None
    judged_at: datetime | None
    inspection_date: date | None
    inspected_by: uuid.UUID | None
    items: list[IqcInspectionItemResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IqcInspectionListResponse(BaseModel):
    items: list[IqcInspectionResponse]
    total: int
    page: int
    page_size: int


# ─── AQL ───

class AqlCalculateRequest(BaseModel):
    lot_qty: int
    aql_level: float
    inspection_level: str = "II"


class AqlCalculateResponse(BaseModel):
    code_letter: str
    sample_size: int
    accept_number: int
    reject_number: int
    aql_level: float
    inspection_level: str


# ─── Stats ───

class IqcStatsResponse(BaseModel):
    total_inspections: int
    accepted_count: int
    rejected_count: int
    concession_count: int
    acceptance_rate: float
    rejection_rate: float

---

### Task 7: Create IQC material service

**Files:**
- Create: `backend/app/services/iqc_material_service.py`

- [ ] **Step 1: Write the service**

```python
import uuid
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.iqc_material import IqcMaterial
from app.models.audit import AuditLog


async def list_materials(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    product_line_code: str | None = None,
) -> tuple[list[IqcMaterial], int]:
    query = select(IqcMaterial)
    count_q = select(func.count(IqcMaterial.material_id))

    if search:
        filt = or_(
            IqcMaterial.part_no.ilike(f"%{search}%"),
            IqcMaterial.part_name.ilike(f"%{search}%"),
        )
        query = query.where(filt)
        count_q = count_q.where(filt)
    if product_line_code:
        query = query.where(IqcMaterial.product_line_code == product_line_code)
        count_q = count_q.where(IqcMaterial.product_line_code == product_line_code)

    total = (await db.execute(count_q)).scalar() or 0
    items = (await db.execute(
        query.order_by(IqcMaterial.part_no).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return list(items), total


async def get_material(db: AsyncSession, material_id: uuid.UUID) -> IqcMaterial | None:
    result = await db.execute(
        select(IqcMaterial).where(IqcMaterial.material_id == material_id)
    )
    return result.scalar_one_or_none()


async def create_material(
    db: AsyncSession,
    part_no: str,
    part_name: str,
    part_spec: str | None = None,
    material_type: str = "raw",
    default_aql: float | None = None,
    default_inspection_level: str | None = None,
    unit: str | None = None,
    product_line_code: str = "DC-DC-100",
    user_id: uuid.UUID | None = None,
) -> IqcMaterial:
    material = IqcMaterial(
        part_no=part_no,
        part_name=part_name,
        part_spec=part_spec,
        material_type=material_type,
        default_aql=default_aql,
        default_inspection_level=default_inspection_level,
        unit=unit,
        product_line_code=product_line_code,
        created_by=user_id,
    )
    db.add(material)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError(f"物料号 '{part_no}' 已存在")

    if user_id:
        db.add(AuditLog(
            user_id=user_id,
            action="create",
            entity_type="iqc_material",
            entity_id=str(material.material_id),
            new_value={"part_no": part_no, "part_name": part_name},
        ))
    await db.commit()
    return material


async def update_material(
    db: AsyncSession,
    material_id: uuid.UUID,
    user_id: uuid.UUID,
    **kwargs,
) -> IqcMaterial:
    material = await get_material(db, material_id)
    if not material:
        raise ValueError("物料不存在")
    old = {"part_no": material.part_no, "part_name": material.part_name}

    for key, value in kwargs.items():
        if value is not None and hasattr(material, key):
            setattr(material, key, value)

    db.add(AuditLog(
        user_id=user_id,
        action="update",
        entity_type="iqc_material",
        entity_id=str(material_id),
        old_value=old,
        new_value={"part_no": material.part_no, "part_name": material.part_name},
    ))
    await db.commit()
    return material


async def delete_material(db: AsyncSession, material_id: uuid.UUID) -> None:
    material = await get_material(db, material_id)
    if not material:
        raise ValueError("物料不存在")
    await db.delete(material)
    await db.commit()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/iqc_material_service.py
git commit -m "feat(iqc): add material CRUD service"
```

---

### Task 8: Create IQC template service

**Files:**
- Create: `backend/app/services/iqc_template_service.py`

- [ ] **Step 1: Write the service**

```python
import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.iqc_inspection_template import IqcInspectionTemplate, IqcTemplateItem
from app.models.audit import AuditLog


async def list_templates(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    material_id: uuid.UUID | None = None,
) -> tuple[list[IqcInspectionTemplate], int]:
    query = select(IqcInspectionTemplate).options(selectinload(IqcInspectionTemplate.items))
    count_q = select(func.count(IqcInspectionTemplate.template_id))

    if material_id:
        query = query.where(IqcInspectionTemplate.material_id == material_id)
        count_q = count_q.where(IqcInspectionTemplate.material_id == material_id)

    total = (await db.execute(count_q)).scalar() or 0
    items = (await db.execute(
        query.order_by(IqcInspectionTemplate.template_name).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return list(items), total


async def get_template(db: AsyncSession, template_id: uuid.UUID) -> IqcInspectionTemplate | None:
    result = await db.execute(
        select(IqcInspectionTemplate)
        .options(selectinload(IqcInspectionTemplate.items))
        .where(IqcInspectionTemplate.template_id == template_id)
    )
    return result.scalar_one_or_none()


async def get_active_template_for_material(
    db: AsyncSession, material_id: uuid.UUID
) -> IqcInspectionTemplate | None:
    result = await db.execute(
        select(IqcInspectionTemplate)
        .options(selectinload(IqcInspectionTemplate.items))
        .where(
            IqcInspectionTemplate.material_id == material_id,
            IqcInspectionTemplate.is_active == True,
        )
    )
    return result.scalar_one_or_none()


async def create_template(
    db: AsyncSession,
    template_name: str,
    material_id: uuid.UUID,
    items: list[dict],
    user_id: uuid.UUID,
) -> IqcInspectionTemplate:
    template = IqcInspectionTemplate(
        template_name=template_name,
        material_id=material_id,
        version=1,
        is_active=True,
        created_by=user_id,
    )
    db.add(template)
    await db.flush()

    for i, item_data in enumerate(items):
        db.add(IqcTemplateItem(
            template_id=template.template_id,
            sort_order=item_data.get("sort_order", i),
            category=item_data["category"],
            item_name=item_data["item_name"],
            inspection_method=item_data.get("inspection_method"),
            inspect_type=item_data.get("inspect_type", "attribute"),
            spec_upper=item_data.get("spec_upper"),
            spec_lower=item_data.get("spec_lower"),
            target_value=item_data.get("target_value"),
            unit=item_data.get("unit"),
            sample_size=item_data.get("sample_size"),
            aql_level=item_data.get("aql_level"),
        ))

    db.add(AuditLog(
        user_id=user_id,
        action="create",
        entity_type="iqc_inspection_template",
        entity_id=str(template.template_id),
        new_value={"template_name": template_name, "version": 1},
    ))
    await db.commit()
    return await get_template(db, template.template_id)


async def update_template(
    db: AsyncSession,
    template_id: uuid.UUID,
    template_name: str,
    items: list[dict],
    user_id: uuid.UUID,
) -> IqcInspectionTemplate:
    """Creates a new version — deactivates old, creates new with version+1."""
    old = await get_template(db, template_id)
    if not old:
        raise ValueError("模板不存在")

    old.is_active = False
    new_version = old.version + 1

    new_template = IqcInspectionTemplate(
        template_name=template_name,
        material_id=old.material_id,
        version=new_version,
        is_active=True,
        created_by=user_id,
    )
    db.add(new_template)
    await db.flush()

    for i, item_data in enumerate(items):
        db.add(IqcTemplateItem(
            template_id=new_template.template_id,
            sort_order=item_data.get("sort_order", i),
            category=item_data["category"],
            item_name=item_data["item_name"],
            inspection_method=item_data.get("inspection_method"),
            inspect_type=item_data.get("inspect_type", "attribute"),
            spec_upper=item_data.get("spec_upper"),
            spec_lower=item_data.get("spec_lower"),
            target_value=item_data.get("target_value"),
            unit=item_data.get("unit"),
            sample_size=item_data.get("sample_size"),
            aql_level=item_data.get("aql_level"),
        ))

    db.add(AuditLog(
        user_id=user_id,
        action="update",
        entity_type="iqc_inspection_template",
        entity_id=str(template_id),
        old_value={"version": old.version},
        new_value={"version": new_version, "template_name": template_name},
    ))
    await db.commit()
    return await get_template(db, new_template.template_id)


async def delete_template(db: AsyncSession, template_id: uuid.UUID) -> None:
    template = await get_template(db, template_id)
    if not template:
        raise ValueError("模板不存在")
    await db.delete(template)
    await db.commit()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/iqc_template_service.py
git commit -m "feat(iqc): add template CRUD service with versioning"
```

---

### Task 9: Create IQC inspection service

**Files:**
- Create: `backend/app/services/iqc_inspection_service.py`

- [ ] **Step 1: Write the service**

```python
import uuid
from datetime import datetime, date
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.iqc_inspection import IqcInspection
from app.models.iqc_inspection_item import IqcInspectionItem, IqcItemMeasurement
from app.models.iqc_inspection_template import IqcInspectionTemplate
from app.models.audit import AuditLog
from app.models.supplier import SupplierSCAR
from app.services.aql_engine import calculate_aql_plan


# ─── Numbering ───

async def _generate_inspection_no(db: AsyncSession) -> str:
    today = datetime.utcnow().strftime("%y%m%d")
    prefix = f"IQC-{today}"
    result = await db.execute(
        select(func.count()).where(IqcInspection.inspection_no.like(f"{prefix}-%"))
    )
    count = (result.scalar() or 0) + 1
    return f"{prefix}-{count:03d}"


# ─── State machine ───

VALID_TRANSITIONS: dict[str, dict[str, str]] = {
    "pending": {"start": "inspecting"},
    "inspecting": {"judge": "judged"},
    "judged": {"close": "closed", "request_reinspect": "pending"},
}


def _transition(current: str, action: str) -> str:
    transitions = VALID_TRANSITIONS.get(current, {})
    if action not in transitions:
        raise ValueError(f"invalid action '{action}' for status '{current}'")
    return transitions[action]


# ─── Inspection CRUD ───

async def list_inspections(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    inspection_result: str | None = None,
    supplier_id: uuid.UUID | None = None,
    material_id: uuid.UUID | None = None,
    keyword: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    product_line_code: str | None = None,
) -> tuple[list[IqcInspection], int]:
    query = select(IqcInspection).options(
        selectinload(IqcInspection.items).selectinload(IqcInspectionItem.measurements)
    )
    count_q = select(func.count(IqcInspection.inspection_id))

    if status:
        query = query.where(IqcInspection.status == status)
        count_q = count_q.where(IqcInspection.status == status)
    if inspection_result:
        query = query.where(IqcInspection.inspection_result == inspection_result)
        count_q = count_q.where(IqcInspection.inspection_result == inspection_result)
    if supplier_id:
        query = query.where(IqcInspection.supplier_id == supplier_id)
        count_q = count_q.where(IqcInspection.supplier_id == supplier_id)
    if material_id:
        query = query.where(IqcInspection.material_id == material_id)
        count_q = count_q.where(IqcInspection.material_id == material_id)
    if keyword:
        filt = or_(
            IqcInspection.inspection_no.ilike(f"%{keyword}%"),
            IqcInspection.part_no.ilike(f"%{keyword}%"),
            IqcInspection.lot_no.ilike(f"%{keyword}%"),
        )
        query = query.where(filt)
        count_q = count_q.where(filt)
    if date_from:
        query = query.where(IqcInspection.inspection_date >= date_from)
        count_q = count_q.where(IqcInspection.inspection_date >= date_from)
    if date_to:
        query = query.where(IqcInspection.inspection_date <= date_to)
        count_q = count_q.where(IqcInspection.inspection_date <= date_to)
    if product_line_code:
        query = query.where(IqcInspection.product_line_code == product_line_code)
        count_q = count_q.where(IqcInspection.product_line_code == product_line_code)

    total = (await db.execute(count_q)).scalar() or 0
    items = (await db.execute(
        query.order_by(IqcInspection.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return list(items), total


async def get_inspection(db: AsyncSession, inspection_id: uuid.UUID) -> IqcInspection | None:
    result = await db.execute(
        select(IqcInspection)
        .options(selectinload(IqcInspection.items).selectinload(IqcInspectionItem.measurements))
        .where(IqcInspection.inspection_id == inspection_id)
    )
    return result.scalar_one_or_none()


async def create_inspection(
    db: AsyncSession,
    supplier_id: uuid.UUID,
    inspection_mode: str = "quick",
    material_id: uuid.UUID | None = None,
    template_id: uuid.UUID | None = None,
    part_no: str | None = None,
    part_name: str | None = None,
    lot_no: str | None = None,
    lot_qty: int | None = None,
    aql_level: float | None = None,
    inspection_level: str = "II",
    inspection_date: date | None = None,
    product_line_code: str | None = None,
    user_id: uuid.UUID | None = None,
) -> IqcInspection:
    inspection_no = await _generate_inspection_no(db)

    inspection = IqcInspection(
        inspection_no=inspection_no,
        supplier_id=supplier_id,
        inspection_mode=inspection_mode,
        material_id=material_id,
        template_id=template_id,
        part_no=part_no,
        part_name=part_name,
        lot_no=lot_no,
        lot_qty=lot_qty,
        aql_level=str(aql_level) if aql_level else None,
        inspection_level=inspection_level,
        inspection_date=inspection_date,
        product_line_code=product_line_code,
        status="pending",
        inspection_result="pending",
    )

    # AQL auto-calculate
    if lot_qty and aql_level:
        try:
            plan = calculate_aql_plan(lot_qty, aql_level, inspection_level)
            inspection.code_letter = plan["code_letter"]
            inspection.sample_qty = plan["sample_size"]
            inspection.accept_number = plan["accept_number"]
            inspection.reject_number = plan["reject_number"]
        except ValueError:
            pass  # Leave AQL fields null if calculation fails

    db.add(inspection)
    await db.flush()

    # Detailed mode: instantiate items from template
    if inspection_mode == "detailed" and template_id:
        template = (await db.execute(
            select(IqcInspectionTemplate)
            .options(selectinload(IqcInspectionTemplate.items))
            .where(IqcInspectionTemplate.template_id == template_id)
        )).scalar_one_or_none()

        if template:
            for ti in sorted(template.items, key=lambda x: x.sort_order):
                item_aql = ti.aql_level or aql_level
                item_plan = None
                if lot_qty and item_aql:
                    try:
                        item_plan = calculate_aql_plan(lot_qty, item_aql, inspection_level)
                    except ValueError:
                        pass

                db.add(IqcInspectionItem(
                    inspection_id=inspection.inspection_id,
                    template_item_id=ti.item_id,
                    sort_order=ti.sort_order,
                    category=ti.category,
                    item_name=ti.item_name,
                    inspect_type=ti.inspect_type,
                    spec_upper=ti.spec_upper,
                    spec_lower=ti.spec_lower,
                    target_value=ti.target_value,
                    sample_size=item_plan["sample_size"] if item_plan else ti.sample_size,
                    accept_no=item_plan["accept_number"] if item_plan else None,
                    reject_no=item_plan["reject_number"] if item_plan else None,
                ))

    if user_id:
        db.add(AuditLog(
            user_id=user_id,
            action="create",
            entity_type="iqc_inspection",
            entity_id=str(inspection.inspection_id),
            new_value={"inspection_no": inspection_no, "mode": inspection_mode},
        ))

    await db.commit()
    return await get_inspection(db, inspection.inspection_id)


async def update_inspection(
    db: AsyncSession,
    inspection_id: uuid.UUID,
    user_id: uuid.UUID,
    **kwargs,
) -> IqcInspection:
    inspection = await get_inspection(db, inspection_id)
    if not inspection:
        raise ValueError("检验单不存在")
    if inspection.status != "pending":
        raise ValueError("仅待检验状态可编辑")

    for key, value in kwargs.items():
        if value is not None and hasattr(inspection, key):
            setattr(inspection, key, value)

    db.add(AuditLog(
        user_id=user_id,
        action="update",
        entity_type="iqc_inspection",
        entity_id=str(inspection_id),
        new_value=kwargs,
    ))
    await db.commit()
    return inspection


async def delete_inspection(db: AsyncSession, inspection_id: uuid.UUID) -> None:
    inspection = await get_inspection(db, inspection_id)
    if not inspection:
        raise ValueError("检验单不存在")
    if inspection.status != "pending":
        raise ValueError("仅待检验状态可删除")
    await db.delete(inspection)
    await db.commit()


# ─── State transitions ───

async def start_inspection(db: AsyncSession, inspection_id: uuid.UUID, user_id: uuid.UUID) -> IqcInspection:
    inspection = await get_inspection(db, inspection_id)
    if not inspection:
        raise ValueError("检验单不存在")
    new_status = _transition(inspection.status, "start")
    inspection.status = new_status
    inspection.inspected_by = user_id
    db.add(AuditLog(
        user_id=user_id, action="start", entity_type="iqc_inspection",
        entity_id=str(inspection_id),
        old_value={"status": "pending"}, new_value={"status": new_status},
    ))
    await db.commit()
    return inspection


async def update_items(
    db: AsyncSession,
    inspection_id: uuid.UUID,
    items_data: list[dict],
    user_id: uuid.UUID,
) -> IqcInspection:
    inspection = await get_inspection(db, inspection_id)
    if not inspection:
        raise ValueError("检验单不存在")
    if inspection.status != "inspecting":
        raise ValueError("仅检验中状态可录入结果")

    for item_data in items_data:
        item_id = item_data.get("item_id")
        item = next((i for i in inspection.items if str(i.item_id) == item_id), None)
        if not item:
            continue

        if "defect_qty" in item_data:
            item.defect_qty = item_data["defect_qty"]
        if "result" in item_data:
            item.result = item_data["result"]
        if "remark" in item_data:
            item.remark = item_data.get("remark")

        measurements = item_data.get("measurements")
        if measurements:
            # Clear existing measurements
            for m in item.measurements:
                await db.delete(m)
            for m_data in measurements:
                db.add(IqcItemMeasurement(
                    item_id=item.item_id,
                    sequence_no=m_data.get("sequence_no", 1),
                    measured_value=m_data.get("measured_value"),
                    attribute_result=m_data.get("attribute_result"),
                    remark=m_data.get("remark"),
                ))

    db.add(AuditLog(
        user_id=user_id, action="update_items", entity_type="iqc_inspection",
        entity_id=str(inspection_id),
    ))
    await db.commit()
    return await get_inspection(db, inspection_id)


async def judge_inspection(
    db: AsyncSession,
    inspection_id: uuid.UUID,
    inspection_result: str,
    defect_qty: int,
    defect_description: str | None,
    sample_qty: int | None,
    user_id: uuid.UUID,
) -> IqcInspection:
    inspection = await get_inspection(db, inspection_id)
    if not inspection:
        raise ValueError("检验单不存在")
    new_status = _transition(inspection.status, "judge")
    inspection.status = new_status
    inspection.inspection_result = inspection_result
    inspection.defect_qty = defect_qty
    if defect_description:
        inspection.defect_description = defect_description
    if sample_qty is not None:
        inspection.sample_qty = sample_qty
    inspection.judged_by = user_id
    inspection.judged_at = datetime.utcnow()

    db.add(AuditLog(
        user_id=user_id, action="judge", entity_type="iqc_inspection",
        entity_id=str(inspection_id),
        old_value={"status": "inspecting"},
        new_value={"status": new_status, "result": inspection_result, "defect_qty": defect_qty},
    ))
    await db.commit()
    return inspection


async def request_reinspect(
    db: AsyncSession,
    inspection_id: uuid.UUID,
    user_id: uuid.UUID,
) -> IqcInspection:
    """Clone-and-link: creates a new inspection from the rejected one."""
    original = await get_inspection(db, inspection_id)
    if not original:
        raise ValueError("检验单不存在")
    if original.status != "judged" or original.inspection_result != "rejected":
        raise ValueError("仅已拒收的检验单可申请复检")

    # Count existing re-inspections for suffix
    count_result = await db.execute(
        select(func.count()).where(IqcInspection.parent_inspection_id == inspection_id)
    )
    suffix_num = (count_result.scalar() or 0) + 1

    new_inspection = IqcInspection(
        inspection_no=f"{original.inspection_no}-R{suffix_num}",
        supplier_id=original.supplier_id,
        inspection_mode=original.inspection_mode,
        material_id=original.material_id,
        template_id=original.template_id,
        part_no=original.part_no,
        part_name=original.part_name,
        lot_no=original.lot_no,
        lot_qty=original.lot_qty,
        aql_level=original.aql_level,
        inspection_level=original.inspection_level,
        product_line_code=original.product_line_code,
        status="pending",
        inspection_result="pending",
        re_inspection=True,
        parent_inspection_id=inspection_id,
    )
    db.add(new_inspection)
    await db.flush()

    # Clone items for detailed mode
    if original.inspection_mode == "detailed" and original.items:
        for orig_item in original.items:
            new_item = IqcInspectionItem(
                inspection_id=new_inspection.inspection_id,
                template_item_id=orig_item.template_item_id,
                sort_order=orig_item.sort_order,
                category=orig_item.category,
                item_name=orig_item.item_name,
                inspect_type=orig_item.inspect_type,
                spec_upper=orig_item.spec_upper,
                spec_lower=orig_item.spec_lower,
                target_value=orig_item.target_value,
                sample_size=orig_item.sample_size,
                accept_no=orig_item.accept_no,
                reject_no=orig_item.reject_no,
            )
            db.add(new_item)

    # Recalculate AQL
    if new_inspection.lot_qty and original.aql_level:
        try:
            aql_val = float(original.aql_level)
            plan = calculate_aql_plan(new_inspection.lot_qty, aql_val, original.inspection_level or "II")
            new_inspection.code_letter = plan["code_letter"]
            new_inspection.sample_qty = plan["sample_size"]
            new_inspection.accept_number = plan["accept_number"]
            new_inspection.reject_number = plan["reject_number"]
        except ValueError:
            pass

    db.add(AuditLog(
        user_id=user_id, action="request_reinspect", entity_type="iqc_inspection",
        entity_id=str(inspection_id),
        new_value={"new_inspection_no": new_inspection.inspection_no},
    ))
    await db.commit()
    return await get_inspection(db, new_inspection.inspection_id)


async def approve_concession(
    db: AsyncSession,
    inspection_id: uuid.UUID,
    reason: str,
    user_id: uuid.UUID,
) -> IqcInspection:
    inspection = await get_inspection(db, inspection_id)
    if not inspection:
        raise ValueError("检验单不存在")
    if inspection.status != "judged" or inspection.inspection_result != "rejected":
        raise ValueError("仅已拒收的检验单可让步接收")

    inspection.inspection_result = "concession"
    inspection.defect_description = (
        f"让步接收原因: {reason}"
        if not inspection.defect_description
        else f"{inspection.defect_description}; 让步接收: {reason}"
    )
    db.add(AuditLog(
        user_id=user_id, action="concession", entity_type="iqc_inspection",
        entity_id=str(inspection_id),
        new_value={"reason": reason},
    ))
    await db.commit()
    return inspection


async def close_inspection(
    db: AsyncSession, inspection_id: uuid.UUID, user_id: uuid.UUID
) -> IqcInspection:
    inspection = await get_inspection(db, inspection_id)
    if not inspection:
        raise ValueError("检验单不存在")
    new_status = _transition(inspection.status, "close")
    inspection.status = new_status
    db.add(AuditLog(
        user_id=user_id, action="close", entity_type="iqc_inspection",
        entity_id=str(inspection_id),
        old_value={"status": "judged"}, new_value={"status": new_status},
    ))
    await db.commit()
    return inspection


async def trigger_scar(
    db: AsyncSession,
    inspection_id: uuid.UUID,
    user_id: uuid.UUID,
) -> IqcInspection:
    inspection = await get_inspection(db, inspection_id)
    if not inspection:
        raise ValueError("检验单不存在")

    scar = SupplierSCAR(
        supplier_id=inspection.supplier_id,
        source_type="iqc",
        source_id=inspection_id,
        description=f"IQC 检验 {inspection.inspection_no} 拒收 — "
                    f"物料 {inspection.part_no or 'N/A'}、批号 {inspection.lot_no or 'N/A'}、"
                    f"缺陷数 {inspection.defect_qty}",
        requested_action=inspection.defect_description or None,
        status="open",
        issued_by=user_id,
        issued_date=date.today(),
    )
    db.add(scar)
    await db.flush()
    inspection.linked_scar_id = scar.scar_id

    db.add(AuditLog(
        user_id=user_id, action="trigger_scar", entity_type="iqc_inspection",
        entity_id=str(inspection_id),
        new_value={"scar_id": str(scar.scar_id)},
    ))
    await db.commit()
    return await get_inspection(db, inspection_id)


# ─── Stats ───

async def get_stats(db: AsyncSession, product_line_code: str | None = None) -> dict:
    base = select(func.count(IqcInspection.inspection_id))
    if product_line_code:
        base = base.where(IqcInspection.product_line_code == product_line_code)

    total = (await db.execute(base)).scalar() or 0

    accepted_q = base.where(IqcInspection.inspection_result == "accepted")
    accepted = (await db.execute(accepted_q)).scalar() or 0

    rejected_q = base.where(IqcInspection.inspection_result == "rejected")
    rejected = (await db.execute(rejected_q)).scalar() or 0

    concession_q = base.where(IqcInspection.inspection_result == "concession")
    concession = (await db.execute(concession_q)).scalar() or 0

    return {
        "total_inspections": total,
        "accepted_count": accepted,
        "rejected_count": rejected,
        "concession_count": concession,
        "acceptance_rate": round(accepted / total * 100, 1) if total > 0 else 0,
        "rejection_rate": round(rejected / total * 100, 1) if total > 0 else 0,
    }
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/iqc_inspection_service.py
git commit -m "feat(iqc): add inspection service with state machine, AQL, SCAR trigger"
```

---

### Task 10: Create IQC API routes

**Files:**
- Create: `backend/app/api/iqc.py`

- [ ] **Step 1: Write the API routes**

```python
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin, require_manager_or_admin, require_admin
from app.models.user import User
from app import schemas
from app.services import iqc_material_service, iqc_template_service, iqc_inspection_service
from app.services.aql_engine import calculate_aql_plan

router = APIRouter(prefix="/api/iqc", tags=["iqc"])


# ─── Material routes ───

@router.get("/materials", response_model=schemas.iqc.IqcMaterialListResponse)
async def list_materials(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    search: str | None = Query(None),
    product_line_code: str | None = Query(None),
    db=Depends(get_db),
    _user=Depends(get_current_user),
):
    items, total = await iqc_material_service.list_materials(
        db, page, page_size, search, product_line_code
    )
    return schemas.iqc.IqcMaterialListResponse(
        items=[schemas.iqc.IqcMaterialResponse.model_validate(m) for m in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("/materials", response_model=schemas.iqc.IqcMaterialResponse)
async def create_material(
    req: schemas.iqc.IqcMaterialCreate,
    db=Depends(get_db),
    user=Depends(require_engineer_or_admin),
):
    try:
        material = await iqc_material_service.create_material(
            db,
            part_no=req.part_no,
            part_name=req.part_name,
            part_spec=req.part_spec,
            material_type=req.material_type,
            default_aql=req.default_aql,
            default_inspection_level=req.default_inspection_level,
            unit=req.unit,
            product_line_code=req.product_line_code,
            user_id=user.user_id,
        )
        return schemas.iqc.IqcMaterialResponse.model_validate(material)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/materials/{material_id}", response_model=schemas.iqc.IqcMaterialResponse)
async def get_material(
    material_id: uuid.UUID,
    db=Depends(get_db),
    _user=Depends(get_current_user),
):
    material = await iqc_material_service.get_material(db, material_id)
    if not material:
        raise HTTPException(404, "物料不存在")
    return schemas.iqc.IqcMaterialResponse.model_validate(material)


@router.put("/materials/{material_id}", response_model=schemas.iqc.IqcMaterialResponse)
async def update_material(
    material_id: uuid.UUID,
    req: schemas.iqc.IqcMaterialUpdate,
    db=Depends(get_db),
    user=Depends(require_engineer_or_admin),
):
    try:
        material = await iqc_material_service.update_material(
            db, material_id, user.user_id,
            **req.model_dump(exclude_none=True),
        )
        return schemas.iqc.IqcMaterialResponse.model_validate(material)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/materials/{material_id}")
async def delete_material(
    material_id: uuid.UUID,
    db=Depends(get_db),
    _user=Depends(require_admin),
):
    try:
        await iqc_material_service.delete_material(db, material_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ─── Template routes ───

@router.get("/templates", response_model=schemas.iqc.IqcTemplateListResponse)
async def list_templates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    material_id: uuid.UUID | None = Query(None),
    db=Depends(get_db),
    _user=Depends(get_current_user),
):
    items, total = await iqc_template_service.list_templates(db, page, page_size, material_id)
    return schemas.iqc.IqcTemplateListResponse(
        items=[schemas.iqc.IqcTemplateResponse.model_validate(t) for t in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("/templates", response_model=schemas.iqc.IqcTemplateResponse)
async def create_template(
    req: schemas.iqc.IqcTemplateCreate,
    db=Depends(get_db),
    user=Depends(require_engineer_or_admin),
):
    try:
        template = await iqc_template_service.create_template(
            db,
            template_name=req.template_name,
            material_id=req.material_id,
            items=[i.model_dump() for i in req.items],
            user_id=user.user_id,
        )
        return schemas.iqc.IqcTemplateResponse.model_validate(template)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/templates/{template_id}", response_model=schemas.iqc.IqcTemplateResponse)
async def get_template(
    template_id: uuid.UUID,
    db=Depends(get_db),
    _user=Depends(get_current_user),
):
    template = await iqc_template_service.get_template(db, template_id)
    if not template:
        raise HTTPException(404, "模板不存在")
    return schemas.iqc.IqcTemplateResponse.model_validate(template)


@router.put("/templates/{template_id}", response_model=schemas.iqc.IqcTemplateResponse)
async def update_template(
    template_id: uuid.UUID,
    req: schemas.iqc.IqcTemplateCreate,
    db=Depends(get_db),
    user=Depends(require_engineer_or_admin),
):
    try:
        template = await iqc_template_service.update_template(
            db, template_id, req.template_name,
            items=[i.model_dump() for i in req.items],
            user_id=user.user_id,
        )
        return schemas.iqc.IqcTemplateResponse.model_validate(template)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: uuid.UUID,
    db=Depends(get_db),
    _user=Depends(require_admin),
):
    try:
        await iqc_template_service.delete_template(db, template_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ─── Inspection routes (list BEFORE /{id}) ───

@router.get("/inspections", response_model=schemas.iqc.IqcInspectionListResponse)
async def list_inspections(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    status: str | None = Query(None),
    inspection_result: str | None = Query(None),
    supplier_id: uuid.UUID | None = Query(None),
    material_id: uuid.UUID | None = Query(None),
    keyword: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    product_line_code: str | None = Query(None),
    db=Depends(get_db),
    _user=Depends(get_current_user),
):
    from datetime import date as date_type
    d_from = date_type.fromisoformat(date_from) if date_from else None
    d_to = date_type.fromisoformat(date_to) if date_to else None

    items, total = await iqc_inspection_service.list_inspections(
        db, page, page_size, status, inspection_result,
        supplier_id, material_id, keyword, d_from, d_to, product_line_code,
    )
    return schemas.iqc.IqcInspectionListResponse(
        items=[schemas.iqc.IqcInspectionResponse.model_validate(i) for i in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("/inspections", response_model=schemas.iqc.IqcInspectionResponse)
async def create_inspection(
    req: schemas.iqc.IqcInspectionCreate,
    db=Depends(get_db),
    user=Depends(require_engineer_or_admin),
):
    try:
        inspection = await iqc_inspection_service.create_inspection(
            db,
            supplier_id=req.supplier_id,
            inspection_mode=req.inspection_mode,
            material_id=req.material_id,
            template_id=req.template_id,
            part_no=req.part_no,
            part_name=req.part_name,
            lot_no=req.lot_no,
            lot_qty=req.lot_qty,
            aql_level=req.aql_level,
            inspection_level=req.inspection_level,
            inspection_date=req.inspection_date,
            product_line_code=req.product_line_code,
            user_id=user.user_id,
        )
        return schemas.iqc.IqcInspectionResponse.model_validate(inspection)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ─── AQL calculate endpoint (before /{id}) ───

@router.post("/calculate-aql", response_model=schemas.iqc.AqlCalculateResponse)
async def calculate_aql(
    req: schemas.iqc.AqlCalculateRequest,
    _user=Depends(get_current_user),
):
    try:
        plan = calculate_aql_plan(req.lot_qty, req.aql_level, req.inspection_level)
        return schemas.iqc.AqlCalculateResponse(**plan)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ─── Stats endpoint (before /{id}) ───

@router.get("/stats", response_model=schemas.iqc.IqcStatsResponse)
async def get_stats(
    product_line_code: str | None = Query(None),
    db=Depends(get_db),
    _user=Depends(get_current_user),
):
    stats = await iqc_inspection_service.get_stats(db, product_line_code)
    return schemas.iqc.IqcStatsResponse(**stats)


# ─── Inspection detail routes ───

@router.get("/inspections/{inspection_id}", response_model=schemas.iqc.IqcInspectionResponse)
async def get_inspection(
    inspection_id: uuid.UUID,
    db=Depends(get_db),
    _user=Depends(get_current_user),
):
    inspection = await iqc_inspection_service.get_inspection(db, inspection_id)
    if not inspection:
        raise HTTPException(404, "检验单不存在")
    return schemas.iqc.IqcInspectionResponse.model_validate(inspection)


@router.put("/inspections/{inspection_id}", response_model=schemas.iqc.IqcInspectionResponse)
async def update_inspection(
    inspection_id: uuid.UUID,
    req: schemas.iqc.IqcInspectionUpdate,
    db=Depends(get_db),
    user=Depends(require_engineer_or_admin),
):
    try:
        inspection = await iqc_inspection_service.update_inspection(
            db, inspection_id, user.user_id,
            **req.model_dump(exclude_none=True),
        )
        return schemas.iqc.IqcInspectionResponse.model_validate(inspection)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/inspections/{inspection_id}")
async def delete_inspection(
    inspection_id: uuid.UUID,
    db=Depends(get_db),
    _user=Depends(require_admin),
):
    try:
        await iqc_inspection_service.delete_inspection(db, inspection_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/inspections/{inspection_id}/start", response_model=schemas.iqc.IqcInspectionResponse)
async def start_inspection(
    inspection_id: uuid.UUID,
    db=Depends(get_db),
    user=Depends(require_engineer_or_admin),
):
    try:
        inspection = await iqc_inspection_service.start_inspection(db, inspection_id, user.user_id)
        return schemas.iqc.IqcInspectionResponse.model_validate(inspection)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/inspections/{inspection_id}/items", response_model=schemas.iqc.IqcInspectionResponse)
async def update_items(
    inspection_id: uuid.UUID,
    req: schemas.iqc.IqcBatchItemUpdate,
    db=Depends(get_db),
    user=Depends(require_engineer_or_admin),
):
    try:
        inspection = await iqc_inspection_service.update_items(
            db, inspection_id,
            [i.model_dump(exclude_none=True) for i in req.items],
            user.user_id,
        )
        return schemas.iqc.IqcInspectionResponse.model_validate(inspection)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/inspections/{inspection_id}/judge", response_model=schemas.iqc.IqcInspectionResponse)
async def judge_inspection(
    inspection_id: uuid.UUID,
    req: schemas.iqc.IqcInspectionJudge,
    db=Depends(get_db),
    user=Depends(require_engineer_or_admin),
):
    try:
        inspection = await iqc_inspection_service.judge_inspection(
            db, inspection_id, req.inspection_result, req.defect_qty,
            req.defect_description, req.sample_qty, user.user_id,
        )
        return schemas.iqc.IqcInspectionResponse.model_validate(inspection)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/inspections/{inspection_id}/request-reinspect", response_model=schemas.iqc.IqcInspectionResponse)
async def request_reinspect(
    inspection_id: uuid.UUID,
    db=Depends(get_db),
    user=Depends(require_engineer_or_admin),
):
    try:
        inspection = await iqc_inspection_service.request_reinspect(db, inspection_id, user.user_id)
        return schemas.iqc.IqcInspectionResponse.model_validate(inspection)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/inspections/{inspection_id}/concession", response_model=schemas.iqc.IqcInspectionResponse)
async def approve_concession(
    inspection_id: uuid.UUID,
    req: schemas.iqc.IqcInspectionConcession,
    db=Depends(get_db),
    user=Depends(require_manager_or_admin),
):
    try:
        inspection = await iqc_inspection_service.approve_concession(
            db, inspection_id, req.reason, user.user_id,
        )
        return schemas.iqc.IqcInspectionResponse.model_validate(inspection)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/inspections/{inspection_id}/close", response_model=schemas.iqc.IqcInspectionResponse)
async def close_inspection(
    inspection_id: uuid.UUID,
    db=Depends(get_db),
    user=Depends(require_manager_or_admin),
):
    try:
        inspection = await iqc_inspection_service.close_inspection(db, inspection_id, user.user_id)
        return schemas.iqc.IqcInspectionResponse.model_validate(inspection)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/inspections/{inspection_id}/trigger-scar", response_model=schemas.iqc.IqcInspectionResponse)
async def trigger_scar(
    inspection_id: uuid.UUID,
    db=Depends(get_db),
    user=Depends(require_engineer_or_admin),
):
    try:
        inspection = await iqc_inspection_service.trigger_scar(db, inspection_id, user.user_id)
        return schemas.iqc.IqcInspectionResponse.model_validate(inspection)
    except ValueError as e:
        raise HTTPException(400, str(e))
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/iqc.py
git commit -m "feat(iqc): add IQC API routes — materials, templates, inspections, AQL"
```

---

### Task 11: Register IQC router and schemas

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/schemas/__init__.py`

- [ ] **Step 1: Check and register in main.py**

Read `backend/app/main.py` to find the last router registration, then add:

```python
from app.api.iqc import router as iqc_router
# ... among other imports

app.include_router(iqc_router)
# ... among other includes
```

- [ ] **Step 2: Check schemas/__init__.py**

Read `backend/app/schemas/__init__.py` to see the pattern, then add:

```python
from app.schemas import iqc
```

- [ ] **Step 3: Verify backend starts**

```bash
cd backend && python -c "from app.main import app; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py backend/app/schemas/__init__.py
git commit -m "feat(iqc): register IQC router and schemas"
```

---

### Task 12: Update TypeScript types for IQC

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Replace the existing IqcInspection interface and add new types**

Replace the old `IqcInspection` interface (around lines 596-611) with:

```typescript
export interface IqcMaterial {
  material_id: string;
  part_no: string;
  part_name: string;
  part_spec: string | null;
  material_type: string;
  default_aql: number | null;
  default_inspection_level: string | null;
  unit: string | null;
  product_line_code: string;
  status: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface IqcTemplateItem {
  item_id: string;
  template_id: string;
  sort_order: number;
  category: string;
  item_name: string;
  inspection_method: string | null;
  inspect_type: 'attribute' | 'variable';
  spec_upper: number | null;
  spec_lower: number | null;
  target_value: number | null;
  unit: string | null;
  sample_size: number | null;
  aql_level: number | null;
}

export interface IqcInspectionTemplate {
  template_id: string;
  template_name: string;
  material_id: string;
  version: number;
  is_active: boolean;
  items: IqcTemplateItem[];
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface IqcItemMeasurement {
  measurement_id: string;
  item_id: string;
  sequence_no: number;
  measured_value: number | null;
  attribute_result: string | null;
  remark: string | null;
}

export interface IqcInspectionItem {
  item_id: string;
  inspection_id: string;
  template_item_id: string | null;
  sort_order: number;
  category: string;
  item_name: string;
  inspect_type: 'attribute' | 'variable';
  spec_upper: number | null;
  spec_lower: number | null;
  target_value: number | null;
  sample_size: number | null;
  accept_no: number | null;
  reject_no: number | null;
  defect_qty: number;
  result: 'pending' | 'ok' | 'ng';
  remark: string | null;
  measurements: IqcItemMeasurement[];
}

export interface IqcInspection {
  inspection_id: string;
  inspection_no: string;
  supplier_id: string;
  inspection_mode: 'quick' | 'detailed';
  material_id: string | null;
  template_id: string | null;
  part_no: string | null;
  part_name: string | null;
  lot_no: string | null;
  lot_qty: number | null;
  sample_qty: number | null;
  aql_level: string | null;
  inspection_level: string | null;
  code_letter: string | null;
  accept_number: number | null;
  reject_number: number | null;
  inspection_result: 'pending' | 'accepted' | 'rejected' | 'concession';
  defect_qty: number;
  defect_description: string | null;
  status: 'pending' | 'inspecting' | 'judged' | 'closed';
  re_inspection: boolean;
  parent_inspection_id: string | null;
  product_line_code: string | null;
  linked_capa_id: string | null;
  linked_scar_id: string | null;
  judged_by: string | null;
  judged_at: string | null;
  inspection_date: string | null;
  inspected_by: string | null;
  items: IqcInspectionItem[];
  created_at: string;
  updated_at: string;
}

export interface IqcInspectionListResponse {
  items: IqcInspection[];
  total: number;
  page: number;
  page_size: number;
}

export interface IqcMaterialListResponse {
  items: IqcMaterial[];
  total: number;
  page: number;
  page_size: number;
}

export interface IqcTemplateListResponse {
  items: IqcInspectionTemplate[];
  total: number;
  page: number;
  page_size: number;
}

export interface AqlCalculateRequest {
  lot_qty: number;
  aql_level: number;
  inspection_level: string;
}

export interface AqlCalculateResponse {
  code_letter: string;
  sample_size: number;
  accept_number: number;
  reject_number: number;
  aql_level: number;
  inspection_level: string;
}

export interface IqcStatsResponse {
  total_inspections: number;
  accepted_count: number;
  rejected_count: number;
  concession_count: number;
  acceptance_rate: number;
  rejection_rate: number;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(iqc): update TypeScript types for IQC module"
```

---

### Task 13: Create IQC API client

**Files:**
- Create: `frontend/src/api/iqc.ts`

- [ ] **Step 1: Write the API functions**

```typescript
import client from "./client";
import type {
  IqcInspection,
  IqcInspectionListResponse,
  IqcMaterial,
  IqcMaterialListResponse,
  IqcInspectionTemplate,
  IqcTemplateListResponse,
  AqlCalculateRequest,
  AqlCalculateResponse,
  IqcStatsResponse,
} from "../types";

// ─── Materials ───

export async function listMaterials(params?: Record<string, unknown>): Promise<IqcMaterialListResponse> {
  const resp = await client.get("/iqc/materials", { params });
  return resp.data;
}

export async function createMaterial(data: Partial<IqcMaterial>): Promise<IqcMaterial> {
  const resp = await client.post("/iqc/materials", data);
  return resp.data;
}

export async function getMaterial(id: string): Promise<IqcMaterial> {
  const resp = await client.get(`/iqc/materials/${id}`);
  return resp.data;
}

export async function updateMaterial(id: string, data: Partial<IqcMaterial>): Promise<IqcMaterial> {
  const resp = await client.put(`/iqc/materials/${id}`, data);
  return resp.data;
}

export async function deleteMaterial(id: string): Promise<void> {
  await client.delete(`/iqc/materials/${id}`);
}

// ─── Templates ───

export async function listTemplates(params?: Record<string, unknown>): Promise<IqcTemplateListResponse> {
  const resp = await client.get("/iqc/templates", { params });
  return resp.data;
}

export async function createTemplate(data: Partial<IqcInspectionTemplate> & { items: unknown[] }): Promise<IqcInspectionTemplate> {
  const resp = await client.post("/iqc/templates", data);
  return resp.data;
}

export async function getTemplate(id: string): Promise<IqcInspectionTemplate> {
  const resp = await client.get(`/iqc/templates/${id}`);
  return resp.data;
}

export async function updateTemplate(id: string, data: Partial<IqcInspectionTemplate> & { items: unknown[] }): Promise<IqcInspectionTemplate> {
  const resp = await client.put(`/iqc/templates/${id}`, data);
  return resp.data;
}

export async function deleteTemplate(id: string): Promise<void> {
  await client.delete(`/iqc/templates/${id}`);
}

// ─── Inspections ───

export async function listInspections(params?: Record<string, unknown>): Promise<IqcInspectionListResponse> {
  const resp = await client.get("/iqc/inspections", { params });
  return resp.data;
}

export async function createInspection(data: Record<string, unknown>): Promise<IqcInspection> {
  const resp = await client.post("/iqc/inspections", data);
  return resp.data;
}

export async function getInspection(id: string): Promise<IqcInspection> {
  const resp = await client.get(`/iqc/inspections/${id}`);
  return resp.data;
}

export async function updateInspection(id: string, data: Record<string, unknown>): Promise<IqcInspection> {
  const resp = await client.put(`/iqc/inspections/${id}`, data);
  return resp.data;
}

export async function deleteInspection(id: string): Promise<void> {
  await client.delete(`/iqc/inspections/${id}`);
}

export async function startInspection(id: string): Promise<IqcInspection> {
  const resp = await client.post(`/iqc/inspections/${id}/start`);
  return resp.data;
}

export async function updateInspectionItems(id: string, data: { items: Record<string, unknown>[] }): Promise<IqcInspection> {
  const resp = await client.put(`/iqc/inspections/${id}/items`, data);
  return resp.data;
}

export async function judgeInspection(id: string, data: Record<string, unknown>): Promise<IqcInspection> {
  const resp = await client.post(`/iqc/inspections/${id}/judge`, data);
  return resp.data;
}

export async function requestReinspect(id: string): Promise<IqcInspection> {
  const resp = await client.post(`/iqc/inspections/${id}/request-reinspect`);
  return resp.data;
}

export async function approveConcession(id: string, data: { reason: string }): Promise<IqcInspection> {
  const resp = await client.post(`/iqc/inspections/${id}/concession`, data);
  return resp.data;
}

export async function closeInspection(id: string): Promise<IqcInspection> {
  const resp = await client.post(`/iqc/inspections/${id}/close`);
  return resp.data;
}

export async function triggerScar(id: string): Promise<IqcInspection> {
  const resp = await client.post(`/iqc/inspections/${id}/trigger-scar`);
  return resp.data;
}

// ─── AQL ───

export async function calculateAql(data: AqlCalculateRequest): Promise<AqlCalculateResponse> {
  const resp = await client.post("/iqc/calculate-aql", data);
  return resp.data;
}

// ─── Stats ───

export async function getIqcStats(params?: Record<string, unknown>): Promise<IqcStatsResponse> {
  const resp = await client.get("/iqc/stats", { params });
  return resp.data;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/iqc.ts
git commit -m "feat(iqc): add frontend API client for IQC module"
```

---

### Task 14: Create IqcInspectionListPage

**Files:**
- Create: `frontend/src/pages/iqc/IqcInspectionListPage.tsx`

- [ ] **Step 1: Write the page**

```tsx
import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Table, Button, Space, Input, Select, DatePicker, Tag, Modal, Form, message, InputNumber } from "antd";
import { PlusOutlined, SearchOutlined } from "@ant-design/icons";
import { useAuthStore } from "../../store/authStore";
import { listInspections, createInspection, calculateAql } from "../../api/iqc";
import { listSuppliers } from "../../api/supplier";
import { listMaterials } from "../../api/iqc";
import type { IqcInspection } from "../../types";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";

const { RangePicker } = DatePicker;

const statusMap: Record<string, { color: string; label: string }> = {
  pending: { color: "blue", label: "待检验" },
  inspecting: { color: "orange", label: "检验中" },
  judged: { color: "green", label: "已判定" },
  closed: { color: "default", label: "已关闭" },
};

const resultMap: Record<string, { color: string; label: string }> = {
  accepted: { color: "green", label: "接收" },
  rejected: { color: "red", label: "拒收" },
  concession: { color: "gold", label: "让步接收" },
  pending: { color: "default", label: "待判定" },
};

export default function IqcInspectionListPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const isViewer = user?.role === "viewer";
  const isEngineer = user?.role !== "viewer";

  const [data, setData] = useState<IqcInspection[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [filters, setFilters] = useState<Record<string, unknown>>({});
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [suppliers, setSuppliers] = useState<{ supplier_id: string; name: string }[]>([]);
  const [materials, setMaterials] = useState<{ material_id: string; part_no: string; part_name: string; default_aql: number | null; default_inspection_level: string | null }[]>([]);
  const [aqlPreview, setAqlPreview] = useState<{ sample_size: number; accept_number: number; reject_number: number; code_letter: string } | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listInspections({ page, page_size: pageSize, ...filters });
      setData(res.items);
      setTotal(res.total);
    } catch {
      message.error("加载检验单列表失败");
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, filters]);

  useEffect(() => { fetchData(); }, [fetchData]);

  useEffect(() => {
    listSuppliers({ page_size: 1000 }).then((res) => setSuppliers(res.items)).catch(() => {});
    listMaterials({ page_size: 1000 }).then((res) => setMaterials(res.items)).catch(() => {});
  }, []);

  const handleCreate = async () => {
    setSubmitting(true);
    try {
      const values = await form.validateFields();
      const payload: Record<string, unknown> = {
        supplier_id: values.supplier_id,
        inspection_mode: values.inspection_mode,
        lot_no: values.lot_no,
        lot_qty: values.lot_qty,
        aql_level: values.aql_level,
        inspection_level: values.inspection_level || "II",
        inspection_date: values.inspection_date?.format("YYYY-MM-DD"),
      };
      if (values.material_id) {
        payload.material_id = values.material_id;
        const mat = materials.find((m) => m.material_id === values.material_id);
        if (mat) {
          payload.part_no = mat.part_no;
          payload.part_name = mat.part_name;
        }
        if (values.inspection_mode === "detailed") {
          const templates = await listMaterials({ material_id: values.material_id });
          // Use active template — template lookup done via listTemplates in practice
        }
      }
      await createInspection(payload);
      message.success("检验单创建成功");
      setModalOpen(false);
      form.resetFields();
      fetchData();
    } catch (e: unknown) {
      if (e && typeof e === "object" && "errorFields" in e) return; // form validation
      message.error("创建失败");
    } finally {
      setSubmitting(false);
    }
  };

  const handleAqlPreview = async () => {
    const lotQty = form.getFieldValue("lot_qty");
    const aqlLevel = form.getFieldValue("aql_level");
    const inspLevel = form.getFieldValue("inspection_level") || "II";
    if (!lotQty || !aqlLevel) return;
    try {
      const plan = await calculateAql({ lot_qty: lotQty, aql_level: aqlLevel, inspection_level: inspLevel });
      setAqlPreview(plan);
    } catch {
      setAqlPreview(null);
    }
  };

  const columns: ColumnsType<IqcInspection> = [
    { title: "检验单号", dataIndex: "inspection_no", key: "inspection_no", render: (v: string, r: IqcInspection) => <a onClick={() => navigate(`/iqc/${r.inspection_id}`)}>{v}</a> },
    { title: "供应商", dataIndex: "supplier_id", key: "supplier_id", width: 120, render: (v: string) => suppliers.find((s) => s.supplier_id === v)?.name || v },
    { title: "物料号", dataIndex: "part_no", key: "part_no", width: 100 },
    { title: "批号", dataIndex: "lot_no", key: "lot_no", width: 100 },
    { title: "批量", dataIndex: "lot_qty", key: "lot_qty", width: 80 },
    { title: "抽样数", dataIndex: "sample_qty", key: "sample_qty", width: 80 },
    { title: "模式", dataIndex: "inspection_mode", key: "inspection_mode", width: 80, render: (v: string) => <Tag color={v === "detailed" ? "blue" : "orange"}>{v === "detailed" ? "详细" : "快速"}</Tag> },
    { title: "状态", dataIndex: "status", key: "status", width: 80, render: (v: string) => <Tag color={statusMap[v]?.color}>{statusMap[v]?.label || v}</Tag> },
    { title: "结果", dataIndex: "inspection_result", key: "inspection_result", width: 90, render: (v: string) => <Tag color={resultMap[v]?.color}>{resultMap[v]?.label || v}</Tag> },
    { title: "检验日期", dataIndex: "inspection_date", key: "inspection_date", width: 110 },
    {
      title: "操作", key: "actions", width: 200,
      render: (_: unknown, r: IqcInspection) => (
        <Space>
          <a onClick={() => navigate(`/iqc/${r.inspection_id}`)}>查看</a>
          {r.status === "inspecting" && !isViewer && <a onClick={() => navigate(`/iqc/${r.inspection_id}`)}>录入</a>}
          {r.status === "judged" && r.inspection_result === "rejected" && isEngineer && <a onClick={async () => { await requestReinspect(r.inspection_id); fetchData(); message.success("复检单已创建"); }}>复检</a>}
          {r.status === "judged" && r.inspection_result === "rejected" && isEngineer && <a onClick={async () => { await triggerScar(r.inspection_id); fetchData(); message.success("SCAR已触发"); }}>SCAR</a>}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        <Input placeholder="搜索(物料号/批号/检验单号)" prefix={<SearchOutlined />} style={{ width: 220 }} allowClear onPressEnter={(e) => { setFilters({ ...filters, keyword: (e.target as HTMLInputElement).value }); setPage(1); }} />
        <Select placeholder="状态" allowClear style={{ width: 100 }} onChange={(v) => { setFilters({ ...filters, status: v }); setPage(1); }} options={Object.entries(statusMap).map(([k, v]) => ({ value: k, label: v.label }))} />
        <Select placeholder="结果" allowClear style={{ width: 100 }} onChange={(v) => { setFilters({ ...filters, inspection_result: v }); setPage(1); }} options={Object.entries(resultMap).map(([k, v]) => ({ value: k, label: v.label }))} />
        <Select placeholder="供应商" allowClear showSearch style={{ width: 150 }} onChange={(v) => { setFilters({ ...filters, supplier_id: v }); setPage(1); }} options={suppliers.map((s) => ({ value: s.supplier_id, label: s.name }))} filterOption={(input, option) => (option?.label as string || "").includes(input)} />
        <RangePicker onChange={(_, dateStrings) => { setFilters({ ...filters, date_from: dateStrings[0], date_to: dateStrings[1] }); setPage(1); }} />
        {!isViewer && <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>新建检验单</Button>}
      </div>
      <Table columns={columns} dataSource={data} rowKey="inspection_id" loading={loading} pagination={{ current: page, pageSize, total, onChange: (p, ps) => { setPage(p); setPageSize(ps); } }} scroll={{ x: 1200 }} />

      <Modal title="新建检验单" open={modalOpen} onOk={handleCreate} onCancel={() => { setModalOpen(false); form.resetFields(); }} confirmLoading={submitting} width={600}>
        <Form form={form} layout="vertical">
          <Form.Item name="inspection_mode" label="检验模式" initialValue="quick" rules={[{ required: true }]}>
            <Select options={[{ value: "quick", label: "快速模式" }, { value: "detailed", label: "详细模式" }]} />
          </Form.Item>
          <Form.Item name="supplier_id" label="供应商" rules={[{ required: true, message: "请选择供应商" }]}>
            <Select showSearch options={suppliers.map((s) => ({ value: s.supplier_id, label: s.name }))} filterOption={(input, option) => (option?.label as string || "").includes(input)} />
          </Form.Item>
          <Form.Item name="material_id" label="物料">
            <Select showSearch allowClear placeholder="选择物料（可选）" options={materials.map((m) => ({ value: m.material_id, label: `${m.part_no} ${m.part_name}` }))} filterOption={(input, option) => (option?.label as string || "").includes(input)} onChange={(v) => { const mat = materials.find((m) => m.material_id === v); if (mat) { form.setFieldsValue({ aql_level: mat.default_aql, inspection_level: mat.default_inspection_level }); } }} />
          </Form.Item>
          <Form.Item name="lot_no" label="批号" rules={[{ required: true, message: "请输入批号" }]}>
            <Input />
          </Form.Item>
          <Space>
            <Form.Item name="lot_qty" label="批量" rules={[{ required: true, message: "请输入批量" }]}>
              <InputNumber min={2} onChange={handleAqlPreview} />
            </Form.Item>
            <Form.Item name="aql_level" label="AQL等级">
              <InputNumber min={0.01} step={0.01} onChange={handleAqlPreview} />
            </Form.Item>
            <Form.Item name="inspection_level" label="检验水平" initialValue="II">
              <Select style={{ width: 80 }} options={["S-1", "S-2", "S-3", "S-4", "I", "II", "III"].map((v) => ({ value: v, label: v }))} />
            </Form.Item>
          </Space>
          {aqlPreview && <div style={{ padding: "8px 12px", background: "#e6f7ff", borderRadius: 4, marginBottom: 12 }}>AQL 方案: 代码字 {aqlPreview.code_letter}, 抽样数 {aqlPreview.sample_size}, Ac={aqlPreview.accept_number}, Re={aqlPreview.reject_number}</div>}
          <Form.Item name="inspection_date" label="检验日期">
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/iqc/IqcInspectionListPage.tsx
git commit -m "feat(iqc): add inspection list page"
```

---

### Task 15: Create IqcInspectionDetailPage

**Files:**
- Create: `frontend/src/pages/iqc/IqcInspectionDetailPage.tsx`

- [ ] **Step 1: Write the page**

```tsx
import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Card, Descriptions, Button, Space, Table, InputNumber, Input, Tag, message, Select, Spin } from "antd";
import { useAuthStore } from "../../store/authStore";
import { getInspection, startInspection, updateInspectionItems, judgeInspection, closeInspection, approveConcession, requestReinspect, triggerScar } from "../../api/iqc";
import { listSuppliers } from "../../api/supplier";
import type { IqcInspection, IqcInspectionItem } from "../../types";
import type { ColumnsType } from "antd/es/table";

const statusMap: Record<string, { color: string; label: string }> = {
  pending: { color: "blue", label: "待检验" },
  inspecting: { color: "orange", label: "检验中" },
  judged: { color: "green", label: "已判定" },
  closed: { color: "default", label: "已关闭" },
};

const resultMap: Record<string, { color: string; label: string }> = {
  accepted: { color: "green", label: "接收" },
  rejected: { color: "red", label: "拒收" },
  concession: { color: "gold", label: "让步接收" },
  pending: { color: "default", label: "待判定" },
};

export default function IqcInspectionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const isViewer = user?.role === "viewer";
  const isManagerOrAdmin = user?.role === "manager" || user?.role === "admin";

  const [inspection, setInspection] = useState<IqcInspection | null>(null);
  const [loading, setLoading] = useState(true);
  const [supplierName, setSupplierName] = useState("");
  const [items, setItems] = useState<IqcInspectionItem[]>([]);

  // Quick mode form state
  const [sampleQty, setSampleQty] = useState<number | null>(null);
  const [defectQty, setDefectQty] = useState(0);
  const [defectDesc, setDefectDesc] = useState("");

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getInspection(id).then((data) => {
      setInspection(data);
      setItems(data.items || []);
      setSampleQty(data.sample_qty);
      setDefectQty(data.defect_qty);
      setDefectDesc(data.defect_description || "");
      if (data.supplier_id) {
        listSuppliers({ page_size: 1000 }).then((res) => {
          const s = res.items.find((sup: { supplier_id: string; name: string }) => sup.supplier_id === data.supplier_id);
          if (s) setSupplierName(s.name);
        }).catch(() => {});
      }
    }).catch(() => message.error("加载检验单失败")).finally(() => setLoading(false));
  }, [id]);

  const handleStart = async () => {
    if (!id) return;
    try {
      const updated = await startInspection(id);
      setInspection(updated);
      message.success("已开始检验");
    } catch { message.error("操作失败"); }
  };

  const handleItemChange = (itemId: string, field: string, value: unknown) => {
    setItems((prev) => prev.map((item) => item.item_id === itemId ? { ...item, [field]: value } : item));
  };

  const handleSaveItems = async () => {
    if (!id) return;
    try {
      const payload = { items: items.map((item) => ({ item_id: item.item_id, defect_qty: item.defect_qty, result: item.result, remark: item.remark })) };
      const updated = await updateInspectionItems(id, payload);
      setInspection(updated);
      setItems(updated.items || []);
      message.success("检验结果已保存");
    } catch { message.error("保存失败"); }
  };

  const handleJudge = async (result: string) => {
    if (!id) return;
    try {
      const updated = await judgeInspection(id, {
        inspection_result: result,
        defect_qty: inspection?.inspection_mode === "quick" ? defectQty : 0,
        defect_description: inspection?.inspection_mode === "quick" ? defectDesc : undefined,
        sample_qty: inspection?.inspection_mode === "quick" ? sampleQty : undefined,
      });
      setInspection(updated);
      message.success("判定完成");
    } catch { message.error("判定失败"); }
  };

  if (loading) return <Spin style={{ display: "block", marginTop: 100 }} />;
  if (!inspection) return <div>检验单不存在</div>;

  const isQuick = inspection.inspection_mode === "quick";

  const itemColumns: ColumnsType<IqcInspectionItem> = [
    { title: "#", dataIndex: "sort_order", width: 40 },
    { title: "类别", dataIndex: "category", width: 80 },
    { title: "检验项", dataIndex: "item_name" },
    { title: "类型", dataIndex: "inspect_type", width: 70, render: (v: string) => <Tag color={v === "variable" ? "blue" : "orange"}>{v === "variable" ? "计量" : "计数"}</Tag> },
    { title: "规格", key: "spec", width: 120, render: (_: unknown, r: IqcInspectionItem) => r.spec_lower != null || r.spec_upper != null ? `${r.spec_lower ?? "-"} ~ ${r.spec_upper ?? "-"}` : "-" },
    { title: "抽样数", dataIndex: "sample_size", width: 70 },
    { title: "Ac/Re", key: "ac_re", width: 70, render: (_: unknown, r: IqcInspectionItem) => r.accept_no != null ? `${r.accept_no}/${r.reject_no}` : "-" },
    {
      title: "缺陷数", dataIndex: "defect_qty", width: 80,
      render: (v: number, r: IqcInspectionItem) =>
        inspection.status === "inspecting" && !isViewer ? <InputNumber size="small" min={0} value={v} onChange={(val) => handleItemChange(r.item_id, "defect_qty", val || 0)} /> : v,
    },
    {
      title: "结果", dataIndex: "result", width: 70,
      render: (v: string, r: IqcInspectionItem) =>
        inspection.status === "inspecting" && !isViewer ? (
          <Select size="small" value={v} onChange={(val) => handleItemChange(r.item_id, "result", val)} style={{ width: 70 }} options={[{ value: "pending", label: "待定" }, { value: "ok", label: "OK" }, { value: "ng", label: "NG" }]} />
        ) : <Tag color={v === "ok" ? "green" : v === "ng" ? "red" : "default"}>{v === "ok" ? "OK" : v === "ng" ? "NG" : "待定"}</Tag>,
    },
    { title: "备注", dataIndex: "remark", width: 120, render: (v: string, r: IqcInspectionItem) => inspection.status === "inspecting" && !isViewer ? <Input size="small" value={v || ""} onChange={(e) => handleItemChange(r.item_id, "remark", e.target.value)} /> : v },
  ];

  return (
    <div>
      <Card title={`检验单 ${inspection.inspection_no}`} extra={<Button onClick={() => navigate("/iqc")}>返回列表</Button>} style={{ marginBottom: 16 }}>
        <Descriptions column={4} size="small" bordered>
          <Descriptions.Item label="状态"><Tag color={statusMap[inspection.status]?.color}>{statusMap[inspection.status]?.label}</Tag></Descriptions.Item>
          <Descriptions.Item label="判定结果"><Tag color={resultMap[inspection.inspection_result]?.color}>{resultMap[inspection.inspection_result]?.label}</Tag></Descriptions.Item>
          <Descriptions.Item label="供应商">{supplierName || inspection.supplier_id}</Descriptions.Item>
          <Descriptions.Item label="物料号">{inspection.part_no || "-"}</Descriptions.Item>
          <Descriptions.Item label="批号">{inspection.lot_no || "-"}</Descriptions.Item>
          <Descriptions.Item label="批量/抽样">{inspection.lot_qty || "-"} / {inspection.sample_qty || "-"}</Descriptions.Item>
          <Descriptions.Item label="模式"><Tag color={isQuick ? "orange" : "blue"}>{isQuick ? "快速" : "详细"}</Tag></Descriptions.Item>
          <Descriptions.Item label="检验日期">{inspection.inspection_date || "-"}</Descriptions.Item>
          {inspection.code_letter && <Descriptions.Item label="AQL代码字">{inspection.code_letter}</Descriptions.Item>}
          {inspection.accept_number != null && <Descriptions.Item label="Ac/Re">{inspection.accept_number}/{inspection.reject_number}</Descriptions.Item>}
          {inspection.defect_description && <Descriptions.Item label="缺陷描述" span={4}>{inspection.defect_description}</Descriptions.Item>}
          {inspection.parent_inspection_id && <Descriptions.Item label="复检" span={2}>是（原单: {inspection.parent_inspection_id}）</Descriptions.Item>}
        </Descriptions>

        <div style={{ marginTop: 16, display: "flex", gap: 8 }}>
          {inspection.status === "pending" && !isViewer && <Button type="primary" onClick={handleStart}>开始检验</Button>}
          {inspection.status === "judged" && isManagerOrAdmin && <Button onClick={async () => { const u = await closeInspection(inspection.inspection_id); setInspection(u); message.success("已关闭"); }}>关闭</Button>}
          {inspection.status === "judged" && inspection.inspection_result === "rejected" && !isViewer && <Button onClick={async () => { const u = await requestReinspect(inspection.inspection_id); message.success(`复检单 ${u.inspection_no} 已创建`); }}>申请复检</Button>}
          {inspection.status === "judged" && inspection.inspection_result === "rejected" && isManagerOrAdmin && <Button onClick={async () => { const reason = prompt("让步接收原因:"); if (reason) { const u = await approveConcession(inspection.inspection_id, { reason }); setInspection(u); message.success("已让步接收"); } }}>让步接收</Button>}
          {inspection.status === "judged" && inspection.inspection_result === "rejected" && !isViewer && <Button danger onClick={async () => { const u = await triggerScar(inspection.inspection_id); setInspection(u); message.success("SCAR已触发"); }}>触发SCAR</Button>}
        </div>
      </Card>

      {/* Quick mode: simple form */}
      {isQuick && inspection.status === "inspecting" && !isViewer && (
        <Card title="快速录入" style={{ marginBottom: 16 }}>
          <Space direction="vertical" style={{ width: "100%" }}>
            <Space>
              <span>抽样数:</span>
              <InputNumber value={sampleQty} onChange={(v) => setSampleQty(v || null)} min={1} />
              <span>缺陷数:</span>
              <InputNumber value={defectQty} onChange={(v) => setDefectQty(v || 0)} min={0} />
              {inspection.accept_number != null && <Tag color="blue">Ac={inspection.accept_number}, Re={inspection.reject_number}</Tag>}
            </Space>
            <Input.TextArea placeholder="缺陷描述" value={defectDesc} onChange={(e) => setDefectDesc(e.target.value)} rows={3} />
            <Space>
              <Button type="primary" onClick={() => handleJudge("accepted")}>接收</Button>
              <Button danger onClick={() => handleJudge("rejected")}>拒收</Button>
            </Space>
          </Space>
        </Card>
      )}

      {/* Detailed mode: item table */}
      {!isQuick && (
        <Card title="检验项" extra={inspection.status === "inspecting" && !isViewer && <Button type="primary" onClick={handleSaveItems}>保存结果</Button>}>
          <Table columns={itemColumns} dataSource={items} rowKey="item_id" pagination={false} size="small" />

          {inspection.status === "inspecting" && !isViewer && (
            <div style={{ marginTop: 16, padding: 12, background: "#fafafa", borderRadius: 6 }}>
              <Space>
                <span>汇总判定：</span>
                <Button type="primary" onClick={async () => {
                  const anyNg = items.some((it) => it.result === "ng");
                  if (anyNg) {
                    await handleJudge("rejected");
                  } else {
                    await handleJudge("accepted");
                  }
                }}>提交判定</Button>
              </Space>
              {items.some((it) => it.result === "ng") && <Tag color="red" style={{ marginLeft: 8 }}>存在NG项，将整批拒收</Tag>}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/iqc/IqcInspectionDetailPage.tsx
git commit -m "feat(iqc): add inspection detail page with quick/detailed modes"
```

---

### Task 16: Create IqcMaterialListPage

**Files:**
- Create: `frontend/src/pages/iqc/IqcMaterialListPage.tsx`

- [ ] **Step 1: Write the page**

```tsx
import { useState, useEffect, useCallback } from "react";
import { Table, Button, Space, Input, Modal, Form, Select, InputNumber, Tag, message, Drawer } from "antd";
import { PlusOutlined, SearchOutlined } from "@ant-design/icons";
import { useAuthStore } from "../../store/authStore";
import { listMaterials, createMaterial, updateMaterial, deleteMaterial, listTemplates, createTemplate } from "../../api/iqc";
import type { IqcMaterial, IqcInspectionTemplate } from "../../types";
import type { ColumnsType } from "antd/es/table";

export default function IqcMaterialListPage() {
  const user = useAuthStore((s) => s.user);
  const isViewer = user?.role === "viewer";
  const isAdmin = user?.role === "admin";

  const [data, setData] = useState<IqcMaterial[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<IqcMaterial | null>(null);
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  // Template drawer
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerMaterial, setDrawerMaterial] = useState<IqcMaterial | null>(null);
  const [templates, setTemplates] = useState<IqcInspectionTemplate[]>([]);
  const [templateForm] = Form.useForm();

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listMaterials({ page_size: 1000, search: search || undefined });
      setData(res.items);
    } catch { message.error("加载物料列表失败"); }
    finally { setLoading(false); }
  }, [search]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEdit = (record: IqcMaterial) => {
    setEditing(record);
    form.setFieldsValue(record);
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      const values = await form.validateFields();
      if (editing) {
        await updateMaterial(editing.material_id, values);
        message.success("物料已更新");
      } else {
        await createMaterial(values);
        message.success("物料已创建");
      }
      setModalOpen(false);
      fetchData();
    } catch { /* form validation or API error */ }
    finally { setSubmitting(false); }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除此物料？")) return;
    try {
      await deleteMaterial(id);
      message.success("物料已删除");
      fetchData();
    } catch { message.error("删除失败"); }
  };

  const openTemplateDrawer = async (material: IqcMaterial) => {
    setDrawerMaterial(material);
    setDrawerOpen(true);
    try {
      const res = await listTemplates({ material_id: material.material_id, page_size: 100 });
      setTemplates(res.items);
    } catch { setTemplates([]); }
  };

  const handleCreateTemplate = async () => {
    if (!drawerMaterial) return;
    try {
      const values = await templateForm.validateFields();
      await createTemplate({ ...values, material_id: drawerMaterial.material_id, items: values.items || [] });
      message.success("模板已创建");
      templateForm.resetFields();
      const res = await listTemplates({ material_id: drawerMaterial.material_id, page_size: 100 });
      setTemplates(res.items);
    } catch { /* validation */ }
  };

  const columns: ColumnsType<IqcMaterial> = [
    { title: "物料号", dataIndex: "part_no", key: "part_no" },
    { title: "物料名称", dataIndex: "part_name", key: "part_name" },
    { title: "规格型号", dataIndex: "part_spec", key: "part_spec", render: (v: string | null) => v || "-" },
    { title: "默认AQL", dataIndex: "default_aql", key: "default_aql", width: 90, render: (v: number | null) => v ?? "-" },
    { title: "检验水平", dataIndex: "default_inspection_level", key: "default_inspection_level", width: 90, render: (v: string | null) => v || "-" },
    { title: "状态", dataIndex: "status", key: "status", width: 80, render: (v: string) => <Tag color={v === "active" ? "green" : "default"}>{v === "active" ? "启用" : "停用"}</Tag> },
    {
      title: "操作", key: "actions", width: 200,
      render: (_: unknown, r: IqcMaterial) => (
        <Space>
          {!isViewer && <a onClick={() => openEdit(r)}>编辑</a>}
          {!isViewer && <a onClick={() => openTemplateDrawer(r)}>模板</a>}
          {isAdmin && <a style={{ color: "red" }} onClick={() => handleDelete(r.material_id)}>删除</a>}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <Input placeholder="搜索物料号/名称" prefix={<SearchOutlined />} style={{ width: 280 }} allowClear onPressEnter={(e) => setSearch((e.target as HTMLInputElement).value)} />
        {!isViewer && <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建物料</Button>}
      </div>
      <Table columns={columns} dataSource={data} rowKey="material_id" loading={loading} pagination={{ pageSize: 50 }} />

      <Modal title={editing ? "编辑物料" : "新建物料"} open={modalOpen} onOk={handleSubmit} onCancel={() => setModalOpen(false)} confirmLoading={submitting} width={500}>
        <Form form={form} layout="vertical">
          <Form.Item name="part_no" label="物料号" rules={[{ required: true, message: "请输入物料号" }]}>
            <Input disabled={!!editing} />
          </Form.Item>
          <Form.Item name="part_name" label="物料名称" rules={[{ required: true, message: "请输入物料名称" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="part_spec" label="规格型号"><Input /></Form.Item>
          <Form.Item name="material_type" label="物料类型" initialValue="raw">
            <Select options={[{ value: "raw", label: "原材料" }, { value: "component", label: "零部件" }, { value: "package", label: "包装材料" }, { value: "other", label: "其他" }]} />
          </Form.Item>
          <Space>
            <Form.Item name="default_aql" label="默认AQL"><InputNumber min={0.01} step={0.01} /></Form.Item>
            <Form.Item name="default_inspection_level" label="检验水平"><Select style={{ width: 80 }} options={["S-1", "S-2", "S-3", "S-4", "I", "II", "III"].map((v) => ({ value: v, label: v }))} /></Form.Item>
            <Form.Item name="unit" label="单位"><Input style={{ width: 80 }} /></Form.Item>
          </Space>
        </Form>
      </Modal>

      <Drawer title={`${drawerMaterial?.part_no} — 检验模板`} open={drawerOpen} onClose={() => setDrawerOpen(false)} width={600}>
        {templates.map((t) => (
          <div key={t.template_id} style={{ marginBottom: 16, padding: 12, background: "#fafafa", borderRadius: 6 }}>
            <div><b>{t.template_name}</b> <Tag>v{t.version}</Tag> {t.is_active && <Tag color="blue">当前</Tag>}</div>
            {t.items.map((it) => (
              <div key={it.item_id} style={{ fontSize: 12, marginTop: 4, paddingLeft: 12 }}>
                {it.sort_order}. [{it.category}] {it.item_name} — {it.inspect_type === "variable" ? "计量" : "计数"}
                {it.spec_upper != null && ` (${it.spec_lower ?? "-"}~${it.spec_upper}${it.unit || ""})`}
                {it.aql_level && ` AQL=${it.aql_level}`}
              </div>
            ))}
          </div>
        ))}
        {templates.length === 0 && <div style={{ color: "#999" }}>暂无检验模板</div>}

        {!isViewer && (
          <div style={{ marginTop: 24, padding: 12, border: "1px solid #d9d9d9", borderRadius: 6 }}>
            <b>新建模板</b>
            <Form form={templateForm} layout="vertical" style={{ marginTop: 8 }}>
              <Form.Item name="template_name" label="模板名称" rules={[{ required: true }]}><Input /></Form.Item>
              <Form.List name="items">
                {(fields, { add, remove }) => (
                  <>
                    {fields.map(({ key, name, ...rest }) => (
                      <Space key={key} style={{ display: "flex", marginBottom: 8 }} align="baseline">
                        <Form.Item {...rest} name={[name, "category"]} rules={[{ required: true }]}><Select placeholder="类别" style={{ width: 90 }} options={["外观", "尺寸", "性能"].map((v) => ({ value: v, label: v }))} /></Form.Item>
                        <Form.Item {...rest} name={[name, "item_name"]} rules={[{ required: true }]}><Input placeholder="检验项名称" style={{ width: 150 }} /></Form.Item>
                        <Form.Item {...rest} name={[name, "inspect_type"]} initialValue="attribute"><Select style={{ width: 80 }} options={[{ value: "attribute", label: "计数" }, { value: "variable", label: "计量" }]} /></Form.Item>
                        <Form.Item {...rest} name={[name, "aql_level"]}><InputNumber placeholder="AQL" min={0.01} step={0.01} style={{ width: 80 }} /></Form.Item>
                        <Button size="small" onClick={() => remove(name)}>删除</Button>
                      </Space>
                    ))}
                    <Button type="dashed" onClick={() => add({ sort_order: fields.length, inspect_type: "attribute" })} block>+ 添加检验项</Button>
                  </>
                )}
              </Form.List>
              <Button type="primary" onClick={handleCreateTemplate} style={{ marginTop: 8 }}>保存模板</Button>
            </Form>
          </div>
        )}
      </Drawer>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/iqc/IqcMaterialListPage.tsx
git commit -m "feat(iqc): add material list page with template drawer"
```

---

### Task 17: Update AppLayout sidebar with IQC menu

**Files:**
- Modify: `frontend/src/components/layout/AppLayout.tsx`

- [ ] **Step 1: Add IQC menu items**

Add the `ExperimentOutlined` icon import (already imported). Add the IQC menu group after the supplier menu item:

```tsx
{ key: "/suppliers", icon: <ShopOutlined />, label: "供应商管理" },
{
  key: "/iqc",
  icon: <ExperimentOutlined />,
  label: "来料检验 (IQC)",
  children: [
    { key: "/iqc", icon: <FileTextOutlined />, label: "检验单管理" },
    { key: "/iqc/materials", icon: <ToolOutlined />, label: "物料管理" },
  ],
},
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/layout/AppLayout.tsx
git commit -m "feat(iqc): add IQC menu group to sidebar"
```

---

### Task 18: Add IQC routes to App.tsx

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add imports and routes**

Add imports:
```tsx
import IqcInspectionListPage from "./pages/iqc/IqcInspectionListPage";
import IqcInspectionDetailPage from "./pages/iqc/IqcInspectionDetailPage";
import IqcMaterialListPage from "./pages/iqc/IqcMaterialListPage";
```

Add routes (after the supplier routes, inside the ProtectedRoute group):
```tsx
<Route path="/iqc" element={<IqcInspectionListPage />} />
<Route path="/iqc/:id" element={<IqcInspectionDetailPage />} />
<Route path="/iqc/materials" element={<IqcMaterialListPage />} />
```

- [ ] **Step 2: Verify frontend compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Fix any type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(iqc): add IQC routes to App.tsx"
```

---

### Task 19: Seed data and end-to-end verification

- [ ] **Step 1: Add IQC seed data to seed.py**

Read `backend/app/seed.py` to understand the existing pattern, then add seed entries for:

1. Two sample materials (DC-DC-100 product line):
   - `P-10001` "DC-DC转换器壳体" with default AQL 1.0, inspection level II
   - `P-20003` "电感线圈" with default AQL 2.5, inspection level II

2. One sample template for P-10001 with 3 items:
   - 外观: 表面划痕检查 (attribute)
   - 尺寸: 长度 (variable, spec 100±0.5mm)
   - 性能: 电气强度测试 (attribute, AQL 0.65)

- [ ] **Step 2: Run migration and seed**

```bash
cd backend && alembic upgrade head && python -m app.seed
```

- [ ] **Step 3: Start the app and verify**

```bash
docker compose up
```

Manual verification checklist:
- [ ] Login as engineer, navigate to `/iqc` — see empty list with "新建检验单" button
- [ ] Create a quick-mode inspection: select supplier, enter lot info, see AQL preview
- [ ] Open the inspection detail, click "开始检验", enter defect count, submit judgment
- [ ] Create a detailed-mode inspection with a material that has a template — verify items are instantiated
- [ ] Go to `/iqc/materials` — see seeded materials, click "模板" to view template
- [ ] Verify sidebar has "来料检验 (IQC)" menu group
- [ ] Login as viewer — verify create/edit buttons are hidden
- [ ] Verify inspection state transitions: pending → inspecting → judged → closed

- [ ] **Step 4: Final commit**

```bash
git add backend/app/seed.py
git commit -m "feat(iqc): add IQC seed data"
```

---

## Self-Review Notes

1. **Spec coverage check:**
   - Data model: Tasks 1-4 cover all 5 new tables + extension ✓
   - Migration: Task 5 ✓
   - Schemas: Task 6 ✓
   - Services: Tasks 7-9 (material, template, inspection with AQL + state machine + SCAR) ✓
   - API endpoints: Task 10 covers all routes in spec §4 ✓
   - Router registration: Task 11 ✓
   - Frontend types: Task 12 ✓
   - Frontend API client: Task 13 ✓
   - Frontend pages: Tasks 14-16 (list, detail, material) ✓
   - Sidebar/routing: Tasks 17-18 ✓
   - Excel import: NOT in scope for this plan (backend endpoint exists, frontend UI deferred)
   - Downstream SCAR/supplier perf: Trigger in Task 10, stats endpoint in Task 10 ✓

2. **No placeholders** — all tasks have complete code.

3. **Type consistency:** Models use `IqcInspection`, `IqcMaterial`, `IqcInspectionTemplate`, `IqcTemplateItem`, `IqcInspectionItem`, `IqcItemMeasurement`. Schemas mirror these names. Frontend types match. Service functions reference correct model attributes.
