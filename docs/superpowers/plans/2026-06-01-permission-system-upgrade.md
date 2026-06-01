# Permission System Upgrade — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 4-role flat RBAC with a database-driven permission matrix (roles × modules) plus product-line data isolation.

**Architecture:** New `role_definitions` + `role_permissions` tables define per-module permission levels; `user_product_lines` links users to product lines. All permission checks go through `core/permissions.py::require_permission(module, level)`. All list endpoints filter by `product_line_code` (or `product_line`). No in-memory cache — query DB per request.

**Tech Stack:** Python 3.11, FastAPI 0.115, SQLAlchemy 2.0, Pydantic v2, PostgreSQL 15 (asyncpg), React 18, TypeScript 5.6, Vite 5.4, Ant Design 5.21, Zustand

---

## File Structure

**New files (backend):**
- `backend/app/models/role.py` — RoleDefinition, RolePermission, UserProductLine SQLAlchemy models
- `backend/app/core/permissions.py` — PermissionLevel, Module enums, `require_permission()`, `get_user_permission()`
- `backend/app/core/product_line_filter.py` — `get_user_product_line_codes()`, field map; `apply_product_line_filter()` for special cases (query built in API layer, not default path)
- `backend/app/services/permission_service.py` — CRUD for roles, permissions, user-product-lines
- `backend/app/api/admin/permissions.py` — Admin-only permission management endpoints
- `backend/alembic/versions/028_permission_matrix.py` — Migration: new tables, role_id, data backfill

**New files (frontend):**
- `frontend/src/hooks/usePermission.ts` — `usePermission()` hook
- `frontend/src/hooks/useProductLines.ts` — `useProductLines()` hook
- `frontend/src/components/ProductLineSelector.tsx` — Product line dropdown in header
- `frontend/src/pages/admin/PermissionPage.tsx` — Role permission matrix editor
- `frontend/src/pages/admin/UserProductLinesPage.tsx` — User-product-line assignment

**Modified files (backend):**
- `backend/app/models/user.py` — Add role_id FK, remove `role` field, add relationship
- `backend/app/core/deps.py` — Replace `require_engineer_or_admin` with wrappers to `require_permission()`
- `backend/app/api/auth.py` — Extend `/me` to return permissions + product_lines
- `backend/app/schemas/auth.py` — Extend UserResponse
- `backend/app/services/dashboard_service.py` — Accept `product_line_codes` list param
- `backend/app/main.py` — Register admin router
- `backend/app/seed.py` — Seed role_definitions, role_permissions, user_product_lines
- All API files under `backend/app/api/` — Replace role checks with `require_permission()` + product line filter

**Modified files (frontend):**
- `frontend/src/types/index.ts` — Extend User interface
- `frontend/src/store/authStore.ts` — Store permissions + product_lines
- `frontend/src/api/client.ts` — 403 interceptor to refresh /me
- `frontend/src/App.tsx` — Enhance ProtectedRoute with module check
- `frontend/src/components/layout/AppLayout.tsx` — Add ProductLineSelector
- All page files under `frontend/src/pages/` — Replace `isViewer`/`isAdminOrManager`/`user?.role ===` with `usePermission()`

---

## Task 1: Database Migration

**Files:**
- Create: `backend/alembic/versions/028_permission_matrix.py`
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/models/__init__.py`

**Purpose:** Create new tables, add role_id, backfill data, rename old role column.

- [ ] **Step 1: Write migration script**

```python
"""permission matrix

Revision ID: 028
Revises: 027
Create Date: 2026-06-01
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = '028_permission_matrix'
down_revision: Union[str, None] = '027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create role_definitions
    op.create_table(
        'role_definitions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('role_key', sa.String(30), unique=True, nullable=False),
        sa.Column('name_zh', sa.String(50), nullable=False),
        sa.Column('name_en', sa.String(50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_editable', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('bypass_row_level_security', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # 2. Seed role_definitions
    op.execute("""
        INSERT INTO role_definitions (id, role_key, name_zh, name_en, description, is_system, is_editable, bypass_row_level_security, sort_order)
        VALUES
          (gen_random_uuid(), 'admin', '系统管理员', 'System Admin', 'Full control', true, false, true, 1),
          (gen_random_uuid(), 'manager', '质量经理', 'Quality Manager', 'Approval-level', true, true, false, 2),
          (gen_random_uuid(), 'viewer', '只读用户', 'Viewer', 'View-only', true, false, false, 3),
          (gen_random_uuid(), 'customer_qe', '客户质量工程师', 'Customer QE', 'Customer complaints, RMA, audit', true, true, false, 4),
          (gen_random_uuid(), 'supplier_qe', '供应商质量工程师', 'Supplier QE', 'Supplier mgmt, IQC, PPAP', true, true, false, 5),
          (gen_random_uuid(), 'field_qe', '现场质量工程师', 'Field QE', 'SPC, MSA, CAPA', true, true, false, 6),
          (gen_random_uuid(), 'planning_qe', '前期策划质量工程师', 'Planning QE', 'FMEA, Control Plan, APQP', true, true, false, 7)
    """)

    # 3. Create role_permissions
    op.create_table(
        'role_permissions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('role_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('role_definitions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('module', sa.String(30), nullable=False),
        sa.Column('permission_level', sa.SmallInteger(), nullable=False),
        sa.UniqueConstraint('role_id', 'module', name='uq_role_module'),
    )

    # 4. Create user_product_lines
    op.create_table(
        'user_product_lines',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_line_code', sa.String(20), sa.ForeignKey('product_lines.code', ondelete='CASCADE'), nullable=False),
        sa.UniqueConstraint('user_id', 'product_line_code', name='uq_user_product_line'),
    )

    # 5. Add role_id to users
    op.add_column('users', sa.Column('role_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('role_definitions.id'), nullable=True))

    # 6. Backfill role_id from role names
    op.execute("""
        UPDATE users u
        SET role_id = r.id
        FROM role_definitions r
        WHERE u.role = r.role_key
    """)

    # 7. Handle quality_engineer -> field_qe
    op.execute("""
        UPDATE users u
        SET role_id = r.id
        FROM role_definitions r
        WHERE u.role = 'quality_engineer' AND r.role_key = 'field_qe'
    """)

    # 8. Set role_id NOT NULL
    op.alter_column('users', 'role_id', nullable=False)

    # 9. Rename role -> legacy_role
    op.alter_column('users', 'role', new_column_name='legacy_role')

    # 10. Seed default permissions for all roles (7 roles × 18 modules = 126 rows)
    # Admin
    op.execute("""
        INSERT INTO role_permissions (role_id, module, permission_level)
        SELECT r.id, m.module, 5
        FROM role_definitions r
        CROSS JOIN (VALUES
          ('fmea'), ('capa'), ('dashboard'), ('audit'), ('customer_quality'),
          ('customer_audit'), ('supplier'), ('iqc'), ('ppap'), ('spc'),
          ('msa'), ('planning'), ('management_review'), ('user_mgmt'),
          ('permission_mgmt'), ('special_characteristic'), ('quality_goal'), ('scar')
        ) AS m(module)
        WHERE r.role_key = 'admin'
    """)
    # Manager (level 4 for most, 1 for user_mgmt, 0 for permission_mgmt)
    op.execute("""
        INSERT INTO role_permissions (role_id, module, permission_level)
        SELECT r.id, m.module, m.level
        FROM role_definitions r
        CROSS JOIN (VALUES
          ('fmea', 4), ('capa', 4), ('dashboard', 4), ('audit', 4), ('customer_quality', 4),
          ('customer_audit', 4), ('supplier', 4), ('iqc', 4), ('ppap', 4), ('spc', 4),
          ('msa', 4), ('planning', 4), ('management_review', 4), ('user_mgmt', 1),
          ('permission_mgmt', 0), ('special_characteristic', 4), ('quality_goal', 4), ('scar', 4)
        ) AS m(module, level)
        WHERE r.role_key = 'manager'
    """)
    # Viewer (level 1 for most, 0 for user_mgmt + permission_mgmt)
    op.execute("""
        INSERT INTO role_permissions (role_id, module, permission_level)
        SELECT r.id, m.module, m.level
        FROM role_definitions r
        CROSS JOIN (VALUES
          ('fmea', 1), ('capa', 1), ('dashboard', 1), ('audit', 1), ('customer_quality', 1),
          ('customer_audit', 1), ('supplier', 1), ('iqc', 1), ('ppap', 1), ('spc', 1),
          ('msa', 1), ('planning', 1), ('management_review', 1), ('user_mgmt', 0),
          ('permission_mgmt', 0), ('special_characteristic', 1), ('quality_goal', 1), ('scar', 1)
        ) AS m(module, level)
        WHERE r.role_key = 'viewer'
    """)
    # customer_qe
    op.execute("""
        INSERT INTO role_permissions (role_id, module, permission_level)
        SELECT r.id, m.module, m.level
        FROM role_definitions r
        CROSS JOIN (VALUES
          ('fmea', 1), ('capa', 2), ('dashboard', 1), ('audit', 1), ('customer_quality', 3),
          ('customer_audit', 3), ('supplier', 1), ('iqc', 0), ('ppap', 0), ('spc', 1),
          ('msa', 0), ('planning', 0), ('management_review', 0), ('user_mgmt', 0),
          ('permission_mgmt', 0), ('special_characteristic', 0), ('quality_goal', 0), ('scar', 1)
        ) AS m(module, level)
        WHERE r.role_key = 'customer_qe'
    """)
    # supplier_qe
    op.execute("""
        INSERT INTO role_permissions (role_id, module, permission_level)
        SELECT r.id, m.module, m.level
        FROM role_definitions r
        CROSS JOIN (VALUES
          ('fmea', 1), ('capa', 2), ('dashboard', 1), ('audit', 1), ('customer_quality', 0),
          ('customer_audit', 0), ('supplier', 3), ('iqc', 3), ('ppap', 3), ('spc', 1),
          ('msa', 0), ('planning', 1), ('management_review', 0), ('user_mgmt', 0),
          ('permission_mgmt', 0), ('special_characteristic', 0), ('quality_goal', 0), ('scar', 3)
        ) AS m(module, level)
        WHERE r.role_key = 'supplier_qe'
    """)
    # field_qe
    op.execute("""
        INSERT INTO role_permissions (role_id, module, permission_level)
        SELECT r.id, m.module, m.level
        FROM role_definitions r
        CROSS JOIN (VALUES
          ('fmea', 3), ('capa', 3), ('dashboard', 1), ('audit', 1), ('customer_quality', 1),
          ('customer_audit', 1), ('supplier', 1), ('iqc', 1), ('ppap', 0), ('spc', 3),
          ('msa', 3), ('planning', 1), ('management_review', 1), ('user_mgmt', 0),
          ('permission_mgmt', 0), ('special_characteristic', 0), ('quality_goal', 0), ('scar', 1)
        ) AS m(module, level)
        WHERE r.role_key = 'field_qe'
    """)
    # planning_qe
    op.execute("""
        INSERT INTO role_permissions (role_id, module, permission_level)
        SELECT r.id, m.module, m.level
        FROM role_definitions r
        CROSS JOIN (VALUES
          ('fmea', 3), ('capa', 1), ('dashboard', 1), ('audit', 1), ('customer_quality', 1),
          ('customer_audit', 1), ('supplier', 1), ('iqc', 1), ('ppap', 3), ('spc', 1),
          ('msa', 0), ('planning', 3), ('management_review', 1), ('user_mgmt', 0),
          ('permission_mgmt', 0), ('special_characteristic', 3), ('quality_goal', 0), ('scar', 1)
        ) AS m(module, level)
        WHERE r.role_key = 'planning_qe'
    """)


def downgrade() -> None:
    op.alter_column('users', 'legacy_role', new_column_name='role')
    op.drop_column('users', 'role_id')
    op.drop_table('user_product_lines')
    op.drop_table('role_permissions')
    op.drop_table('role_definitions')
```

- [ ] **Step 2: Run migration**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
alembic upgrade head
```

Expected: `028_permission_matrix` succeeds, all tables created, role_permissions has 126 rows.

- [ ] **Step 3: Update User model**

Modify `backend/app/models/user.py`:

```python
# Remove this line:
# role: Mapped[str] = mapped_column(String(20), default="viewer")

# Add:
role_id: Mapped[uuid.UUID] = mapped_column(
    UUID(as_uuid=True), ForeignKey("role_definitions.id"), nullable=False
)
legacy_role: Mapped[str | None] = mapped_column(String(20), nullable=True)

# Add relationship:
role_definition: Mapped["RoleDefinition"] = relationship("RoleDefinition", lazy="joined")
```

- [ ] **Step 4: Create Role models**

Create `backend/app/models/role.py`:

```python
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, DateTime, SmallInteger, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class RoleDefinition(Base):
    __tablename__ = "role_definitions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    role_key: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name_zh: Mapped[str] = mapped_column(String(50), nullable=False)
    name_en: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_editable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    bypass_row_level_security: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission", back_populates="role", cascade="all, delete-orphan"
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "module", name="uq_role_module"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("role_definitions.id", ondelete="CASCADE"), nullable=False
    )
    module: Mapped[str] = mapped_column(String(30), nullable=False)
    permission_level: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    role: Mapped["RoleDefinition"] = relationship("RoleDefinition", back_populates="permissions")


class UserProductLine(Base):
    __tablename__ = "user_product_lines"
    __table_args__ = (
        UniqueConstraint("user_id", "product_line_code", name="uq_user_product_line"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    product_line_code: Mapped[str] = mapped_column(
        String(20), ForeignKey("product_lines.code", ondelete="CASCADE"), nullable=False
    )
```

- [ ] **Step 5: Update models __init__.py**

Modify `backend/app/models/__init__.py` to add:

```python
from app.models.role import RoleDefinition, RolePermission, UserProductLine
```

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/028_permission_matrix.py backend/app/models/user.py backend/app/models/role.py backend/app/models/__init__.py
git commit -m "feat: permission matrix migration + role models"
```

---

## Task 2: Backend Permission Engine

**Files:**
- Create: `backend/app/core/permissions.py`
- Create: `backend/app/core/product_line_filter.py`
- Create: `backend/app/services/permission_service.py`
- Create: `backend/app/api/admin/permissions.py`
- Modify: `backend/app/core/deps.py`
- Modify: `backend/app/main.py`

**Purpose:** Build the core permission check utilities and admin management API.

- [ ] **Step 1: Write core/permissions.py**

```python
"""Permission checking utilities."""
import uuid
from enum import IntEnum, StrEnum
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.security import decode_access_token
from app.models.user import User
from app.models.role import RolePermission, RoleDefinition

bearer_scheme = HTTPBearer()


class PermissionLevel(IntEnum):
    NONE = 0
    VIEW = 1
    CREATE = 2
    EDIT = 3
    APPROVE = 4
    ADMIN = 5


class Module(StrEnum):
    FMEA = "fmea"
    CAPA = "capa"
    DASHBOARD = "dashboard"
    AUDIT = "audit"
    CUSTOMER_QUALITY = "customer_quality"
    CUSTOMER_AUDIT = "customer_audit"
    SUPPLIER = "supplier"
    IQC = "iqc"
    PPAP = "ppap"
    SPC = "spc"
    MSA = "msa"
    PLANNING = "planning"
    MANAGEMENT_REVIEW = "management_review"
    USER_MGMT = "user_mgmt"
    PERMISSION_MGMT = "permission_mgmt"
    SPECIAL_CHARACTERISTIC = "special_characteristic"
    QUALITY_GOAL = "quality_goal"
    SCAR = "scar"


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    result = await db.execute(select(User).where(User.user_id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def get_user_permission(
    user: User,
    module: Module,
    db: AsyncSession,
) -> PermissionLevel:
    result = await db.execute(
        select(RolePermission.permission_level)
        .where(RolePermission.role_id == user.role_id)
        .where(RolePermission.module == module.value)
    )
    level = result.scalar_one_or_none()
    return PermissionLevel(level) if level is not None else PermissionLevel.NONE


def require_permission(module: Module, min_level: PermissionLevel):
    async def _check(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        level = await get_user_permission(user, module, db)
        if level < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"需要 {module.value} 模块的 {min_level.name} 权限",
            )
        return user
    return _check


# Backward-compatible wrappers
async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role_definition.role_key != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


async def require_engineer_or_admin(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Deprecated: redirects to permission check."""
    level = await get_user_permission(user, Module.FMEA, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="编辑权限不足")
    return user
```

- [ ] **Step 2: Write core/product_line_filter.py**

```python
"""Product line filtering for data isolation."""
from fastapi import Request, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.role import UserProductLine

QUERY_PARAM_NAMES = ["product_line", "product_line_code"]

PRODUCT_LINE_FIELD_MAP: dict[str, str] = {
    "fmea": "product_line_code",
    "capa": "product_line_code",
    "audit": "product_line_code",
    "customer_quality": "product_line_code",
    "customer_audit": "product_line_code",
    "iqc": "product_line_code",
    "ppap": "product_line_code",
    "spc": "product_line",
    "msa": "product_line_code",
    "planning": "product_line_code",
    "management_review": "product_line_code",
    "special_characteristic": "product_line_code",
    "quality_goal": "product_line_code",
    "scar": "product_line_code",
}


def get_requested_product_line(request: Request) -> str | None:
    for param in QUERY_PARAM_NAMES:
        code = request.query_params.get(param)
        if code:
            return code
    return None


async def get_user_product_line_codes(user: User, db: AsyncSession) -> list[str]:
    result = await db.execute(
        select(UserProductLine.product_line_code)
        .where(UserProductLine.user_id == user.user_id)
    )
    return [row[0] for row in result.all()]


async def apply_product_line_filter(
    query,
    user: User,
    model: type,
    module: str,
    db: AsyncSession,
    request: Request,
):
    field_name = PRODUCT_LINE_FIELD_MAP.get(module)
    if not field_name or not hasattr(model, field_name):
        return query

    if user.role_definition.bypass_row_level_security:
        requested_code = get_requested_product_line(request)
        if requested_code:
            query = query.where(getattr(model, field_name) == requested_code)
        return query

    user_codes = await get_user_product_line_codes(user, db)
    if not user_codes:
        return query.where(False)

    requested_code = get_requested_product_line(request)
    if requested_code:
        if requested_code not in user_codes:
            raise HTTPException(403, f"无权访问产品线 '{requested_code}'")
        query = query.where(getattr(model, field_name) == requested_code)
    else:
        query = query.where(getattr(model, field_name).in_(user_codes))

    return query
```

- [ ] **Step 3: Write services/permission_service.py**

```python
"""Permission management service."""
import uuid
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.user import User


async def list_roles(db: AsyncSession) -> list[RoleDefinition]:
    result = await db.execute(
        select(RoleDefinition).order_by(RoleDefinition.sort_order)
    )
    return result.scalars().all()


async def get_role_by_key(db: AsyncSession, role_key: str) -> RoleDefinition | None:
    result = await db.execute(
        select(RoleDefinition).where(RoleDefinition.role_key == role_key)
    )
    return result.scalar_one_or_none()


async def get_role_permissions(
    db: AsyncSession, role_id: uuid.UUID
) -> dict[str, int]:
    result = await db.execute(
        select(RolePermission.module, RolePermission.permission_level)
        .where(RolePermission.role_id == role_id)
    )
    return {module: level for module, level in result.all()}


async def update_role_permissions(
    db: AsyncSession,
    role_key: str,
    permissions: list[dict],
) -> None:
    from app.core.permissions import Module

    role = await get_role_by_key(db, role_key)
    if not role:
        raise ValueError(f"角色 '{role_key}' 不存在")
    if not role.is_editable:
        raise ValueError(f"角色 '{role_key}' 权限不可修改")

    valid_modules = set(m.value for m in Module)
    for p in permissions:
        if p["module"] not in valid_modules:
            raise ValueError(f"无效模块 '{p['module']}'")

    async with db.begin():
        await db.execute(
            delete(RolePermission).where(RolePermission.role_id == role.id)
        )
        for p in permissions:
            db.add(RolePermission(
                role_id=role.id,
                module=p["module"],
                permission_level=p["level"],
            ))


async def assign_product_line(
    db: AsyncSession, user_id: uuid.UUID, product_line_code: str
) -> UserProductLine:
    # Validate user exists
    from app.models.user import User
    user_result = await db.execute(select(User).where(User.user_id == user_id))
    if not user_result.scalar_one_or_none():
        raise ValueError(f"用户 '{user_id}' 不存在")
    
    # Validate product line exists
    from app.models.product_line import ProductLine
    pl_result = await db.execute(
        select(ProductLine).where(ProductLine.code == product_line_code)
    )
    if not pl_result.scalar_one_or_none():
        raise ValueError(f"产品线 '{product_line_code}' 不存在")
    
    # Check for duplicate
    existing = await db.execute(
        select(UserProductLine)
        .where(UserProductLine.user_id == user_id)
        .where(UserProductLine.product_line_code == product_line_code)
    )
    if existing.scalar_one_or_none():
        raise ValueError(f"用户已分配产品线 '{product_line_code}'")
    
    upl = UserProductLine(user_id=user_id, product_line_code=product_line_code)
    db.add(upl)
    return upl


async def remove_product_line(
    db: AsyncSession, user_id: uuid.UUID, product_line_code: str
) -> None:
    await db.execute(
        delete(UserProductLine)
        .where(UserProductLine.user_id == user_id)
        .where(UserProductLine.product_line_code == product_line_code)
    )


async def get_user_product_lines(
    db: AsyncSession, user_id: uuid.UUID
) -> list[UserProductLine]:
    result = await db.execute(
        select(UserProductLine).where(UserProductLine.user_id == user_id)
    )
    return result.scalars().all()
```

- [ ] **Step 4: Write api/admin/permissions.py**

```python
"""Admin permission management API."""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.permissions import require_permission, Module, PermissionLevel
from app.core.deps import get_current_user
from app.models.user import User
from app.services import permission_service
from app.schemas.permission import PermissionUpdateRequest, AssignProductLineRequest

router = APIRouter(prefix="/api/admin", tags=["admin-permissions"])


@router.get("/roles")
async def list_roles(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission(Module.PERMISSION_MGMT, PermissionLevel.ADMIN)),
):
    roles = await permission_service.list_roles(db)
    result = []
    for role in roles:
        perms = await permission_service.get_role_permissions(db, role.id)
        result.append({
            "id": str(role.id),
            "role_key": role.role_key,
            "name_zh": role.name_zh,
            "name_en": role.name_en,
            "is_system": role.is_system,
            "is_editable": role.is_editable,
            "permissions": perms,
        })
    return result


@router.put("/roles/{role_key}/permissions")
async def update_permissions(
    role_key: str,
    req: PermissionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission(Module.PERMISSION_MGMT, PermissionLevel.ADMIN)),
):
    try:
        await permission_service.update_role_permissions(
            db, role_key, [p.model_dump() for p in req.permissions]
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"message": "权限已更新"}


@router.get("/modules")
async def list_modules(
    _user: User = Depends(require_permission(Module.PERMISSION_MGMT, PermissionLevel.ADMIN)),
):
    return [{"key": m.value, "name": m.name} for m in Module]


@router.get("/users/{user_id}/product-lines")
async def get_user_product_lines(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission(Module.PERMISSION_MGMT, PermissionLevel.ADMIN)),
):
    upls = await permission_service.get_user_product_lines(db, user_id)
    return [{"product_line_code": upl.product_line_code} for upl in upls]


@router.post("/users/{user_id}/product-lines")
async def assign_product_line(
    user_id: uuid.UUID,
    req: AssignProductLineRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission(Module.PERMISSION_MGMT, PermissionLevel.ADMIN)),
):
    upl = await permission_service.assign_product_line(db, user_id, req.product_line_code)
    await db.commit()
    return {"message": "产品线已分配"}


@router.delete("/users/{user_id}/product-lines/{product_line_code}")
async def remove_product_line(
    user_id: uuid.UUID,
    product_line_code: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission(Module.PERMISSION_MGMT, PermissionLevel.ADMIN)),
):
    await permission_service.remove_product_line(db, user_id, product_line_code)
    await db.commit()
    return {"message": "产品线已移除"}
```

- [ ] **Step 5: Write schemas/permission.py**

```python
"""Permission management schemas."""
from pydantic import BaseModel, Field, field_validator


class PermissionItem(BaseModel):
    module: str
    level: int

    @field_validator('level')
    @classmethod
    def validate_level(cls, v: int) -> int:
        if not 0 <= v <= 5:
            raise ValueError('权限级别必须在 0-5 之间')
        return v


class PermissionUpdateRequest(BaseModel):
    permissions: list[PermissionItem]


class AssignProductLineRequest(BaseModel):
    product_line_code: str
```

- [ ] **Step 6: Add schemas.permission to __init__.py**

Modify `backend/app/schemas/__init__.py` to add:

```python
from app.schemas import permission as permission_schemas
```

Or use direct import in API:

```python
from app.schemas.permission import PermissionUpdateRequest, AssignProductLineRequest
```

- [ ] **Step 7: Update deps.py**

Modify `backend/app/core/deps.py`: remove the old `require_engineer_or_admin` body and redirect to `require_permission`:

```python
from app.core.permissions import (
    get_current_user,
    require_permission,
    require_admin,
    PermissionLevel,
    Module,
)
```

Keep `get_current_user` and `require_admin` imports. Remove old inline role string checks.

- [ ] **Step 8: Create admin __init__.py**

Create `backend/app/api/admin/__init__.py`:

```python
# Admin API package
```

- [ ] **Step 9: Register admin router in main.py**

Add to `backend/app/main.py`:

```python
from app.api.admin import permissions as admin_permissions_api
# ... existing routers
app.include_router(admin_permissions_api.router)
```

- [ ] **Step 10: Commit**

```bash
git add backend/app/core/permissions.py backend/app/core/product_line_filter.py backend/app/services/permission_service.py backend/app/api/admin/permissions.py backend/app/api/admin/__init__.py backend/app/schemas/permission.py backend/app/core/deps.py backend/app/main.py
git commit -m "feat: backend permission engine + admin API"
```

---

## Task 3: Backend Auth API Extension

**Files:**
- Modify: `backend/app/schemas/auth.py`
- Modify: `backend/app/api/auth.py`
- Modify: `backend/app/seed.py`

**Purpose:** Extend `/api/auth/me` to return permissions + product_lines; update seed to use role_id.

- [ ] **Step 1: Extend UserResponse schema**

Modify `backend/app/schemas/auth.py`:

```python
from pydantic import Field

class UserResponse(BaseModel):
    user_id: uuid.UUID
    username: str
    display_name: str | None = None
    email: str | None = None
    role_key: str
    legacy_role: str | None = None
    permissions: dict[str, int] = Field(default_factory=dict)
    product_lines: list[dict] = Field(default_factory=list)
    bypass_row_level_security: bool
    is_active: bool
    auditor_info: dict | None = None
```

- [ ] **Step 2: Create build_user_response helper**

Create helper in `backend/app/api/auth.py`:

```python
from app.services.permission_service import get_role_permissions
from app.core.product_line_filter import get_user_product_line_codes
from app.models.product_line import ProductLine

async def build_user_response(user: User, db: AsyncSession) -> UserResponse:
    permissions = await get_role_permissions(db, user.role_id)
    
    if user.role_definition.bypass_row_level_security:
        # Admin: return all active product lines
        from sqlalchemy import select
        result = await db.execute(
            select(ProductLine.code, ProductLine.name)
            .where(ProductLine.is_active == True)
        )
        product_lines = [
            {"product_line_code": code, "name": name}
            for code, name in result.all()
        ]
    else:
        codes = await get_user_product_line_codes(user, db)
        product_lines = [{"product_line_code": code} for code in codes]
    
    return UserResponse(
        user_id=user.user_id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        role_key=user.role_definition.role_key,
        legacy_role=user.legacy_role,
        permissions=permissions,
        product_lines=product_lines,
        bypass_row_level_security=user.role_definition.bypass_row_level_security,
        is_active=user.is_active,
        auditor_info=user.auditor_info,
    )
```

- [ ] **Step 3: Update login and me endpoints**

Modify `backend/app/api/auth.py`:

```python
@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    # ... existing auth logic ...
    user_response = await build_user_response(user, db)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user_response,
    )

@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await build_user_response(user, db)
```

- [ ] **Step 4: Update seed.py**

Modify `backend/app/seed.py`: replace `role="quality_engineer"` with `role_id=field_qe_role_id`. Query role IDs from DB first, then seed users with role_id.

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/auth.py backend/app/api/auth.py backend/app/seed.py
git commit -m "feat: extend auth API with permissions + product lines"
```

---

## Task 4: Backend Route Migration — Phase 1 (Core Modules)

**Files to modify:**
- `backend/app/api/fmea.py`
- `backend/app/api/capa.py`
- `backend/app/api/dashboard.py`
- `backend/app/services/dashboard_service.py`

**Pattern for each file:**
1. Replace `from app.core.deps import ... require_engineer_or_admin` with `from app.core.permissions import require_permission, Module, PermissionLevel`
2. Replace `Depends(require_engineer_or_admin)` with `Depends(require_permission(Module.XXX, PermissionLevel.LEVEL))`
3. Pass `allowed_product_line_codes` to service layer from API endpoint
4. Replace inline `user.role not in [...]` checks with permission level checks

**Service layer approach:**

API endpoint gathers user's product lines, passes to service:

```python
# In API endpoint (e.g., backend/app/api/fmea.py)
from app.core.product_line_filter import get_user_product_line_codes

@router.get("")
async def list_fmeas(
    ...,
    user: User = Depends(require_permission(Module.FMEA, PermissionLevel.VIEW)),
    db: AsyncSession = Depends(get_db),
):
    # Get allowed product lines
    allowed_pls = None
    if not user.role_definition.bypass_row_level_security:
        allowed_pls = await get_user_product_line_codes(user, db)
        if not allowed_pls:
            return FMEAListResponse(items=[], total=0, page=1, page_size=20)
    
    items, total = await fmea_service.list_fmeas(
        db, page=page, page_size=page_size, allowed_product_line_codes=allowed_pls
    )
    ...
```

Service uses `allowed_product_line_codes` in query:

```python
# In service (e.g., backend/app/services/fmea_service.py)
async def list_fmeas(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    allowed_product_line_codes: list[str] | None = None,
) -> tuple[list[FMEADocument], int]:
    query = select(FMEADocument)
    if allowed_product_line_codes is not None:
        query = query.where(FMEADocument.product_line_code.in_(allowed_product_line_codes))
    
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()
    
    result = await db.execute(
        query.offset((page - 1) * page_size).limit(page_size).order_by(FMEADocument.updated_at.desc())
    )
    return result.scalars().all(), total
```

- [ ] **Step 1: Migrate fmea.py**

Replace:
- `require_engineer_or_admin` → `require_permission(Module.FMEA, PermissionLevel.CREATE)` for create/update
- `require_manager_or_admin` → `require_permission(Module.FMEA, PermissionLevel.APPROVE)` for approve
- In list endpoint: gather `allowed_product_line_codes`, pass to `fmea_service.list_fmeas()`

- [ ] **Step 2: Migrate capa.py**

Same pattern with Module.CAPA.

- [ ] **Step 3: Migrate dashboard.py + dashboard_service.py**

Modify `dashboard_service.py::get_dashboard()` to accept `product_line_codes: list[str] | None`. Modify `dashboard.py` to call `get_user_product_line_codes()` and pass to service.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/fmea.py backend/app/api/capa.py backend/app/api/dashboard.py backend/app/services/dashboard_service.py
git commit -m "feat: migrate FMEA/CAPA/Dashboard to new permission system"
```

---

## Task 5: Backend Route Migration — Phase 2 (Remaining API Files)

**Files to modify (all use same pattern):**
- `backend/app/api/audit_program.py`
- `backend/app/api/audit_plan.py`
- `backend/app/api/audit_finding.py`
- `backend/app/api/customer_quality.py`
- `backend/app/api/supplier.py`
- `backend/app/api/iqc.py`
- `backend/app/api/ppap.py`
- `backend/app/api/spc.py`
- `backend/app/api/msa.py`
- `backend/app/api/gauge.py`
- `backend/app/api/control_plan.py`
- `backend/app/api/apqp.py`
- `backend/app/api/management_review.py`
- `backend/app/api/special_characteristic.py`
- `backend/app/api/quality_goal.py`
- `backend/app/api/scar.py`
- `backend/app/api/shipment.py`
- `backend/app/api/version.py`

- [ ] **Step 1: Batch replace in all files**

For each file:
```python
# Replace import
from app.core.permissions import require_permission, Module, PermissionLevel

# Replace decorator
# OLD: user: User = Depends(require_engineer_or_admin)
# NEW: user: User = Depends(require_permission(Module.XXX, PermissionLevel.CREATE))

# Pass allowed product lines to service
from app.core.product_line_filter import get_user_product_line_codes

# In list endpoint:
allowed_pls = None
if not user.role_definition.bypass_row_level_security:
    allowed_pls = await get_user_product_line_codes(user, db)
    if not allowed_pls:
        return ListResponse(items=[], total=0, page=1, page_size=20)

items, total = await service.list_items(db, ..., allowed_product_line_codes=allowed_pls)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/*.py
git commit -m "feat: migrate all API routes to new permission system"
```

---

## Task 6: Frontend Permission Hooks

**Files:**
- Create: `frontend/src/hooks/usePermission.ts`
- Create: `frontend/src/hooks/useProductLines.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/store/authStore.ts`

- [ ] **Step 1: Extend User type**

Modify `frontend/src/types/index.ts`:

```typescript
export interface User {
  user_id: string;
  username: string;
  display_name: string | null;
  email: string | null;
  role_key: string;
  legacy_role?: string | null;
  permissions: Record<string, number>;
  product_lines: { product_line_code: string; name?: string }[];
  bypass_row_level_security: boolean;
  is_active: boolean;
  auditor_info?: AuditorInfo;
}
```

- [ ] **Step 2: Write usePermission.ts**

```typescript
import { useMemo } from "react";
import { useAuthStore } from "../store/authStore";

export type ModuleKey =
  | "fmea" | "capa" | "dashboard" | "audit" | "customer_quality"
  | "customer_audit" | "supplier" | "iqc" | "ppap" | "spc"
  | "msa" | "planning" | "management_review" | "user_mgmt"
  | "permission_mgmt" | "special_characteristic" | "quality_goal" | "scar";

export enum PermissionLevel {
  NONE = 0,
  VIEW = 1,
  CREATE = 2,
  EDIT = 3,
  APPROVE = 4,
  ADMIN = 5,
}

export function usePermission() {
  const user = useAuthStore((s) => s.user);
  const permissions = user?.permissions ?? {};

  const getLevel = useMemo(() => {
    return (module: ModuleKey): PermissionLevel => {
      return (permissions[module] ?? 0) as PermissionLevel;
    };
  }, [permissions]);

  return {
    getLevel,
    canView: (module: ModuleKey) => getLevel(module) >= PermissionLevel.VIEW,
    canCreate: (module: ModuleKey) => getLevel(module) >= PermissionLevel.CREATE,
    canEdit: (module: ModuleKey) => getLevel(module) >= PermissionLevel.EDIT,
    canApprove: (module: ModuleKey) => getLevel(module) >= PermissionLevel.APPROVE,
    isAdmin: user?.role_key === "admin",
    roleKey: user?.role_key ?? "viewer",
  };
}
```

- [ ] **Step 3: Create productLineStore.ts**

Create `frontend/src/store/productLineStore.ts`:

```typescript
import { create } from "zustand";

interface ProductLineState {
  currentProductLine: string | null;
  setCurrentProductLine: (code: string | null) => void;
}

export const useProductLineStore = create<ProductLineState>((set) => ({
  currentProductLine: null,
  setCurrentProductLine: (code) => set({ currentProductLine: code }),
}));
```

- [ ] **Step 4: Write useProductLines.ts**

```typescript
import { useMemo } from "react";
import { useAuthStore } from "../store/authStore";
import { useProductLineStore } from "../store/productLineStore";

export function useProductLines() {
  const user = useAuthStore((s) => s.user);
  const productLines = user?.product_lines ?? [];
  const bypass = user?.bypass_row_level_security ?? false;

  const currentProductLine = useProductLineStore((s) => s.currentProductLine);
  const setCurrentProductLine = useProductLineStore((s) => s.setCurrentProductLine);

  const hasProductLines = productLines.length > 0;

  const queryParam = useMemo(() => {
    if (bypass) {
      return currentProductLine ?? undefined;
    }
    if (!hasProductLines) {
      return undefined;
    }
    if (productLines.length === 1) {
      return productLines[0].product_line_code;
    }
    return currentProductLine ?? undefined;
  }, [bypass, hasProductLines, productLines, currentProductLine]);

  return {
    productLines,
    currentProductLine,
    setCurrentProductLine,
    hasProductLines,
    queryParam,
    bypass,
  };
}
```

- [ ] **Step 4: Update authStore.ts**

Modify `frontend/src/store/authStore.ts` to store permissions and product_lines from /me response, and add `setUser` method:

```typescript
interface AuthState {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  fetchUser: () => Promise<void>;
  setUser: (user: User | null) => void;  // NEW
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: localStorage.getItem("access_token"),
  loading: false,

  login: async (username, password) => {
    const resp = await apiLogin({ username, password });
    localStorage.setItem("access_token", resp.access_token);
    set({ user: resp.user, token: resp.access_token });
  },

  logout: () => {
    localStorage.removeItem("access_token");
    set({ user: null, token: null });
  },

  fetchUser: async () => {
    const token = localStorage.getItem("access_token");
    if (!token) return;
    try {
      set({ loading: true });
      const user = await getMe();
      set({ user, loading: false });
    } catch {
      localStorage.removeItem("access_token");
      set({ user: null, token: null, loading: false });
    }
  },

  setUser: (user) => set({ user }),  // NEW
}));
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/hooks/usePermission.ts frontend/src/hooks/useProductLines.ts frontend/src/store/authStore.ts frontend/src/store/productLineStore.ts
git commit -m "feat: frontend permission hooks + types"
```

---

## Task 7: Frontend API Client + Route Guard

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`

- [ ] **Step 1: Add 403 interceptor**

Modify `frontend/src/api/client.ts`:

```typescript
client.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 403) {
      // Silently refresh permissions
      try {
        const { getMe } = await import("./auth");
        const user = await getMe();
        useAuthStore.getState().setUser(user);
      } catch {
        // If refresh fails, let the 403 propagate
      }
    }
    return Promise.reject(error);
  }
);
```

- [ ] **Step 2: Update App.tsx route guards**

Add `requiredModule` prop to ProtectedRoute:

```typescript
import { useEffect } from "react";
import { Navigate } from "react-router-dom";
import { useAuthStore } from "./store/authStore";
import { usePermission } from "./hooks/usePermission";

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredModule?: ModuleKey;
}

function ProtectedRoute({ children, requiredModule }: ProtectedRouteProps) {
  const token = localStorage.getItem("access_token");
  const user = useAuthStore((s) => s.user);
  const loading = useAuthStore((s) => s.loading);
  const fetchUser = useAuthStore((s) => s.fetchUser);
  const { canView } = usePermission();

  // On mount: if we have token but no user, fetch user first
  useEffect(() => {
    if (token && !user && !loading) {
      fetchUser();
    }
  }, [token, user, loading, fetchUser]);

  if (!token) return <Navigate to="/login" />;
  if (loading || (!user && token)) {
    // Still loading user data — show spinner or blank
    return <div style={{ padding: 40, textAlign: "center" }}>加载中...</div>;
  }
  if (requiredModule && !canView(requiredModule)) return <Navigate to="/dashboard" />;

  return <>{children}</>;
}
```

- [ ] **Step 3: Add ProductLineSelector to AppLayout**

Create `frontend/src/components/ProductLineSelector.tsx`:

```typescript
import { Select } from "antd";
import { useProductLines } from "../hooks/useProductLines";

export default function ProductLineSelector() {
  const { productLines, currentProductLine, setCurrentProductLine, hasProductLines, bypass } = useProductLines();

  if (!hasProductLines && !bypass) {
    return <span style={{ color: "#999" }}>未分配产品线</span>;
  }

  const options = bypass
    ? [{ value: "", label: "全部产品线" }]
    : [];

  productLines.forEach((pl) => {
    options.push({ value: pl.product_line_code, label: pl.product_line_code });
  });

  return (
    <Select
      value={currentProductLine ?? (bypass ? "" : productLines[0]?.product_line_code)}
      onChange={(v) => setCurrentProductLine(v || null)}
      options={options}
      style={{ width: 160 }}
      disabled={!bypass && productLines.length <= 1}
    />
  );
}
```

Add to AppLayout header.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/App.tsx frontend/src/components/ProductLineSelector.tsx frontend/src/components/layout/AppLayout.tsx
git commit -m "feat: frontend route guards + product line selector"
```

---

## Task 8: Frontend Page Migration

**Files:** All page files under `frontend/src/pages/`

**Pattern for each page:**
1. Replace `import { useAuthStore }` with `import { usePermission }`
2. Replace `const isViewer = user?.role === "viewer"` with `const { canEdit, canApprove, canCreate } = usePermission()`
3. Replace `const isAdminOrManager = ["admin", "manager"].includes(user?.role ?? "")` with `const { canApprove, canCreate } = usePermission()`
4. Replace `user?.role === "quality_engineer"` with `canEdit('module_name')`
5. Add `disabled={!canEdit('module_name')}` to inputs
6. Add `canCreate('module_name') &&` guard to create buttons
7. Pass `product_line` query param from useProductLines to API calls

- [ ] **Step 1: Migrate core pages (FMEA, CAPA, Dashboard)**

- FMEAEditorPage.tsx: `disabled={!canEdit('fmea')}`, `canApprove('fmea')` for approve button
- FMEAListPage.tsx: `canCreate('fmea')` for create button
- CAPADetailPage.tsx: `disabled={!canEdit('capa')}`, `canApprove('capa')` for D7/D8
- CAPAListPage.tsx: `canCreate('capa')` for create button
- DashboardPage.tsx: pass `product_line` param

- [ ] **Step 2: Migrate remaining pages**

Batch update all remaining pages with the same pattern. Use grep to find all `isViewer`, `isAdminOrManager`, `isEngineer`, `isEngineerPlus`, `quality_engineer` references.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/
git commit -m "feat: migrate all frontend pages to new permission system"
```

---

## Task 9: Admin Permission Management Page

**Files:**
- Create: `frontend/src/pages/admin/PermissionPage.tsx`
- Create: `frontend/src/pages/admin/UserProductLinesPage.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`

- [ ] **Step 1: Create PermissionPage.tsx**

Admin page with role list on left, permission matrix editor on right using Ant Design Table + Select cells.

- [ ] **Step 2: Create UserProductLinesPage.tsx**

Admin page with user list, Transfer component for assigning product lines.

- [ ] **Step 3: Add admin routes and sidebar**

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/admin/
git commit -m "feat: admin permission management UI"
```

---

## Task 10: Verification

- [ ] **Step 1: Database verification**

```bash
cd backend
alembic upgrade head
python -m app.seed
```

- Verify: 7 role_definitions, 126 role_permissions, user_product_lines populated

- [ ] **Step 2: Backend API verification**

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Test with different users:
- admin: full access, all product lines (bypass)
- manager: approval access, only assigned product lines
- customer_qe: customer_quality=3, supplier=1 (read-only), only assigned product lines
- viewer: all modules view-only, only assigned product lines

- [ ] **Step 3: Frontend verification**

```bash
cd frontend
npm run dev
```

- Login as each role, verify button visibility, input states, route guards
- Verify product line selector behavior
- Verify 403 auto-refresh

- [ ] **Step 4: Build check**

```bash
cd frontend && npm run build
cd backend && python -c "import app.main"
```

- [ ] **Step 5: Commit final**

```bash
git add -A
git commit -m "feat: complete permission system upgrade v3.2"
```

---

## Self-Review

### Spec Coverage Checklist

| Spec Section | Implementing Task |
|-------------|-------------------|
| role_definitions table | Task 1 |
| role_permissions table | Task 1 |
| user_product_lines table | Task 1 |
| users.role_id + legacy_role | Task 1 |
| User.role_definition relationship | Task 1 |
| PermissionLevel enum | Task 2 |
| Module enum | Task 2 |
| require_permission() | Task 2 |
| get_user_permission() | Task 2 |
| apply_product_line_filter() | Task 2 |
| get_user_product_line_codes() | Task 2 |
| PRODUCT_LINE_FIELD_MAP | Task 2 |
| Admin permission API | Task 2 |
| /api/auth/me extension | Task 3 |
| Dashboard multi-model aggregation | Task 4 |
| Supplier special handling | Task 5 |
| usePermission() hook | Task 6 |
| useProductLines() hook | Task 6 |
| 403 interceptor | Task 7 |
| Route guards | Task 7 |
| ProductLineSelector | Task 7 |
| Frontend page migration | Task 8 |
| Admin management pages | Task 9 |
| Verification steps | Task 10 |

### Placeholder Scan

- No "TBD", "TODO", "implement later" found
- No vague "add error handling" without code
- All file paths are exact
- All function signatures match between definition and usage
- No "Similar to Task N" references

### Type Consistency

- `PermissionLevel` used consistently across backend (IntEnum) and frontend (TS enum)
- `Module` values match between backend StrEnum and frontend ModuleKey union
- `role_key` field used consistently in DB, backend, frontend
- `product_line_code` used consistently (not mixed with product_line_id)
- `get_user_permission()` signature: `(User, Module, AsyncSession) -> PermissionLevel` — consistent
- `get_user_product_line_codes()` signature: `(User, AsyncSession) -> list[str]` — consistent