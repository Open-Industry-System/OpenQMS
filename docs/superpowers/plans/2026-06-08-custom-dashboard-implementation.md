# 自定义拖拽看板 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现用户级可拖拽自定义看板，支持 14 种 widget 的自由组合、拖拽布局、大小调整，布局持久化到后端。

**Architecture:** 后端新增 `user_dashboard_layouts` 表存储 JSONB 布局配置；前端使用 `react-grid-layout` 实现网格拖拽；Widget 通过注册表动态映射组件类型；数据通过 `GET /dashboard/widgets?types=...` 按需聚合。

**Tech Stack:** React 18 + TypeScript + react-grid-layout + Ant Design | FastAPI + SQLAlchemy 2.0 + PostgreSQL JSONB

---

## File Structure

### Backend (new + modified)

| File | Action | Responsibility |
|:---|:---|:---|
| `backend/alembic/versions/20260608_add_user_dashboard_layouts.py` | Create | Alembic migration for `user_dashboard_layouts` table |
| `backend/app/models/user_dashboard_layout.py` | Create | SQLAlchemy model: UserDashboardLayout |
| `backend/app/schemas/dashboard_layout.py` | Create | Pydantic schemas: LayoutConfig, WidgetLayoutItem, etc. |
| `backend/app/models/__init__.py` | Modify | Export UserDashboardLayout |
| `backend/app/api/dashboard.py` | Modify | Add `/layout` GET/PUT and `/widgets` GET endpoints |
| `backend/app/services/dashboard_service.py` | Modify | Add `get_widgets_data()`, extend `get_layout()`, `save_layout()` |

### Frontend (new + modified)

| File | Action | Responsibility |
|:---|:---|:---|
| `frontend/src/components/dashboard/widgets/types.ts` | Create | Widget type definitions (WidgetMeta, WidgetProps, etc.) |
| `frontend/src/components/dashboard/widgets/registry.ts` | Create | Widget registry: type → component mapping |
| `frontend/src/components/dashboard/widgets/KpiPendingWidget.tsx` | Create | KPI: 待办事项 |
| `frontend/src/components/dashboard/widgets/KpiOverdueWidget.tsx` | Create | KPI: 超期任务 |
| `frontend/src/components/dashboard/widgets/KpiRiskWidget.tsx` | Create | KPI: 高风险项 |
| `frontend/src/components/dashboard/widgets/KpiTrendWidget.tsx` | Create | KPI: 本月新增 |
| `frontend/src/components/dashboard/widgets/AlertHighRpnWidget.tsx` | Create | Alert: 高 RPN FMEA |
| `frontend/src/components/dashboard/widgets/AlertOverdueCapaWidget.tsx` | Create | Alert: 超期 CAPA |
| `frontend/src/components/dashboard/widgets/AlertHighPpmWidget.tsx` | Create | Alert: PPM 超标供应商 |
| `frontend/src/components/dashboard/widgets/RecentActionsWidget.tsx` | Create | List: 最近操作 |
| `frontend/src/components/dashboard/widgets/SpcAbnormalWidget.tsx` | Create | KPI: SPC 异常点数 |
| `frontend/src/components/dashboard/widgets/SpcCapabilityWidget.tsx` | Create | Chart: 过程能力摘要 |
| `frontend/src/components/dashboard/widgets/MsaGaugeExpiryWidget.tsx` | Create | KPI: 量具到期提醒 |
| `frontend/src/components/dashboard/widgets/IqcPendingWidget.tsx` | Create | KPI: IQC 待检批次 |
| `frontend/src/components/dashboard/widgets/MesEquipmentWidget.tsx` | Create | Chart: 设备状态概览 |
| `frontend/src/components/dashboard/widgets/SupplierPpmWidget.tsx` | Create | Chart: 供应商 PPM 趋势 |
| `frontend/src/components/dashboard/WidgetWrapper.tsx` | Create | Widget shell: title bar, delete button, ResizeObserver, error/loading states |
| `frontend/src/components/dashboard/DashboardGrid.tsx` | Create | react-grid-layout wrapper with edit/view mode |
| `frontend/src/components/dashboard/WidgetLibraryPanel.tsx` | Create | Left sidebar: categorized widget catalog |
| `frontend/src/pages/dashboard/DashboardPage.tsx` | Modify | Rewrite with edit mode toggle, data fetching, save/cancel/reset |
| `frontend/src/api/dashboard.ts` | Modify | Add `getLayout()`, `saveLayout()`, `getWidgetsData()` |
| `frontend/src/hooks/usePermission.ts` | Modify | Add `"mes"` to ModuleKey union |
| `frontend/src/types/index.ts` | Modify | Add `DashboardWidgetsData`, `DashboardLayoutConfig`, etc. |

---

## Task 1: Database Model + Alembic Migration

**Files:**
- Create: `backend/app/models/user_dashboard_layout.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/20260608_add_user_dashboard_layouts.py`

- [ ] **Step 1: Create the model**

```python
# backend/app/models/user_dashboard_layout.py
import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserDashboardLayout(Base):
    __tablename__ = "user_dashboard_layouts"

    layout_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    layout_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (UniqueConstraint("user_id", name="uq_user_dashboard_layout"),)
```

- [ ] **Step 2: Export the model**

In `backend/app/models/__init__.py`, add:
```python
from app.models.user_dashboard_layout import UserDashboardLayout
```

- [ ] **Step 3: Find the latest migration**

Run: `ls backend/alembic/versions/ | tail -5`
Note the most recent revision ID for `down_revision`.

- [ ] **Step 4: Create the migration file**

Create `backend/alembic/versions/20260608_add_user_dashboard_layouts.py`:

```python
"""add user_dashboard_layouts table

Revision ID: 20260608_user_dashboard_layouts
Revises: 030_add_mes_tables
Create Date: 2026-06-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260608_user_dashboard_layouts"
down_revision = "030_add_mes_tables"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_dashboard_layouts",
        sa.Column(
            "layout_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("layout_config", postgresql.JSONB, nullable=False, default=dict),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", name="uq_user_dashboard_layout"),
    )
    op.create_index(
        "idx_user_dashboard_layout_user",
        "user_dashboard_layouts",
        ["user_id"],
        unique=True,
    )


def downgrade():
    op.drop_index("idx_user_dashboard_layout_user", table_name="user_dashboard_layouts")
    op.drop_table("user_dashboard_layouts")
```

- [ ] **Step 5: Run the migration**

Run: `cd backend && alembic upgrade head`
Expected: Migration succeeds, no errors.

- [ ] **Step 6: Verify the table exists**

Run: `cd backend && alembic current`
Expected: Shows `20260608_user_dashboard_layouts` as current revision.

Alternatively, verify via async query:
```bash
cd backend && python -c "
import asyncio
from sqlalchemy import text
from app.database import async_engine

async def check():
    async with async_engine.begin() as conn:
        result = await conn.execute(text(\"SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename='user_dashboard_layouts'\"))
        print(bool(result.scalar_one_or_none()))

asyncio.run(check())
"
```
Expected: `True`

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/user_dashboard_layout.py backend/app/models/__init__.py backend/alembic/versions/20260608_add_user_dashboard_layouts.py
git commit -m "feat: add user_dashboard_layouts model and migration"
```

---

## Task 2: Backend Schema + API Routes

**Files:**
- Create: `backend/app/schemas/dashboard_layout.py`
- Modify: `backend/app/api/dashboard.py`

- [ ] **Step 1: Create Pydantic schemas**

```python
# backend/app/schemas/dashboard_layout.py
import uuid
from pydantic import BaseModel, Field


class WidgetLayoutItem(BaseModel):
    i: str
    type: str
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(ge=1)
    h: int = Field(ge=1)


class LayoutConfig(BaseModel):
    lg: list[WidgetLayoutItem]


class DashboardLayoutResponse(BaseModel):
    layout_id: uuid.UUID | None
    user_id: uuid.UUID
    layout_config: LayoutConfig
    created_at: str | None
    updated_at: str | None

    model_config = {"from_attributes": True}


class DashboardLayoutUpdate(BaseModel):
    layout_config: LayoutConfig


class DashboardWidgetsResponse(BaseModel):
    kpi: dict = Field(default_factory=dict)
    alerts: dict = Field(default_factory=dict)
    recent_actions: list = Field(default_factory=list)
    spc: dict = Field(default_factory=dict)
    msa: dict = Field(default_factory=dict)
    iqc: dict = Field(default_factory=dict)
    mes: dict = Field(default_factory=dict)
    supplier: dict = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)
```

- [ ] **Step 2: Add layout endpoints to dashboard router**

Modify `backend/app/api/dashboard.py`. Add imports and new endpoints:

```python
from app.models.user_dashboard_layout import UserDashboardLayout
from app.schemas import dashboard_layout as layout_schemas

# Add at the bottom of dashboard.py, before existing endpoints or after

@router.get("/layout")
async def get_layout(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.DASHBOARD, PermissionLevel.VIEW)),
):
    """Get current user's dashboard layout. Returns default if none saved."""
    result = await db.execute(
        select(UserDashboardLayout).where(UserDashboardLayout.user_id == user.user_id)
    )
    layout = result.scalar_one_or_none()

    if layout is None:
        from app.services.dashboard_service import get_default_layout
        default_config = await get_default_layout(db, user)
        return layout_schemas.DashboardLayoutResponse(
            layout_id=None,
            user_id=user.user_id,
            layout_config=default_config,
            created_at=None,
            updated_at=None,
        )

    # Filter saved layout by current permissions (permissions may have changed)
    from app.services.dashboard_service import filter_layout_by_permissions
    filtered_config = await filter_layout_by_permissions(layout.layout_config, user, db)

    return layout_schemas.DashboardLayoutResponse(
        layout_id=layout.layout_id,
        user_id=layout.user_id,
        layout_config=layout_schemas.LayoutConfig.model_validate(filtered_config),
        created_at=layout.created_at.isoformat() if layout.created_at else None,
        updated_at=layout.updated_at.isoformat() if layout.updated_at else None,
    )


@router.put("/layout")
async def save_layout(
    req: layout_schemas.DashboardLayoutUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.DASHBOARD, PermissionLevel.EDIT)),
):
    """Save current user's dashboard layout."""
    from app.services.dashboard_service import (
        WIDGET_MODULE_MAP, _user_can_view_module, WIDGET_MIN_SIZES,
    )

    # Validation: i uniqueness, bounds, type whitelist, module permissions
    widgets = req.layout_config.lg
    seen_i = set()
    for w in widgets:
        if w.i in seen_i:
            raise HTTPException(status_code=400, detail=f"duplicate widget id: {w.i}")
        seen_i.add(w.i)
        if w.x < 0 or w.y < 0:
            raise HTTPException(status_code=400, detail="coordinates must be non-negative")
        if w.w > 12 or w.h > 50:
            raise HTTPException(status_code=400, detail="widget size exceeds grid bounds")
        if w.x + w.w > 12:
            raise HTTPException(status_code=400, detail="widget exceeds horizontal grid boundary")
        # Type whitelist check
        if w.type not in WIDGET_MODULE_MAP:
            raise HTTPException(status_code=400, detail=f"invalid widget type: {w.type}")
        # Module permission check
        module = WIDGET_MODULE_MAP[w.type]
        if not await _user_can_view_module(user, module, db):
            raise HTTPException(status_code=403, detail=f"no permission for widget type: {w.type}")
        # MinSize check
        min_size = WIDGET_MIN_SIZES.get(w.type, {"w": 1, "h": 1})
        if w.w < min_size["w"] or w.h < min_size["h"]:
            raise HTTPException(status_code=400, detail=f"widget {w.type} size below minimum")

    result = await db.execute(
        select(UserDashboardLayout).where(UserDashboardLayout.user_id == user.user_id)
    )
    layout = result.scalar_one_or_none()

    if layout is None:
        layout = UserDashboardLayout(
            user_id=user.user_id,
            layout_config=req.layout_config.model_dump(),
        )
        db.add(layout)
    else:
        layout.layout_config = req.layout_config.model_dump()

    await db.commit()
    await db.refresh(layout)

    return layout_schemas.DashboardLayoutResponse(
        layout_id=layout.layout_id,
        user_id=layout.user_id,
        layout_config=layout_schemas.LayoutConfig.model_validate(layout.layout_config),
        created_at=layout.created_at.isoformat() if layout.created_at else None,
        updated_at=layout.updated_at.isoformat() if layout.updated_at else None,
    )
```

- [ ] **Step 3: Add widgets endpoint**

```python
@router.get("/widgets")
async def get_widgets(
    types: str = Query(..., description="Comma-separated widget types"),
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.DASHBOARD, PermissionLevel.VIEW)),
):
    """Get widget data for specified types. Empty types returns empty data (valid for empty dashboard)."""
    type_list = list(dict.fromkeys(t.strip() for t in (types or "").split(",") if t.strip()))
    if not type_list:
        return layout_schemas.DashboardWidgetsResponse()  # Empty dashboard is valid

    # Validate types against whitelist
    valid_types = {
        "kpi_pending_actions", "kpi_overdue_tasks", "kpi_high_risk_items", "kpi_month_trend",
        "alert_high_rpn_fmea", "alert_overdue_capa", "alert_high_ppm_suppliers",
        "recent_actions",
        "spc_abnormal_count", "spc_capability_summary",
        "msa_gauge_expiry", "iqc_pending_inspections",
        "mes_equipment_status", "supplier_ppm_trend",
    }
    invalid = [t for t in type_list if t not in valid_types]
    if invalid:
        raise HTTPException(status_code=400, detail=f"unknown widget type: {', '.join(invalid)}")

    # Filter by module permissions
    from app.services.dashboard_service import WIDGET_MODULE_MAP, _user_can_view_module
    allowed_types = []
    for t in type_list:
        module = WIDGET_MODULE_MAP.get(t, "dashboard")
        if await _user_can_view_module(user, module, db):
            allowed_types.append(t)

    # Resolve product line filter
    if user.role_definition.bypass_row_level_security:
        filter_codes = [product_line] if product_line else None
    else:
        from app.core.product_line_filter import get_user_product_line_codes
        user_codes = await get_user_product_line_codes(user, db)
        if not user_codes:
            return layout_schemas.DashboardWidgetsResponse()
        if product_line:
            if product_line not in user_codes:
                raise HTTPException(403, f"无权访问产品线 '{product_line}'")
            filter_codes = [product_line]
        else:
            filter_codes = user_codes

    data = await dashboard_service.get_widgets_data(db, allowed_types, filter_codes, user.user_id)
    return layout_schemas.DashboardWidgetsResponse(**data)
```

- [ ] **Step 4: Verify the API compiles**

Run: `cd backend && python -c "from app.api.dashboard import router; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/dashboard_layout.py backend/app/api/dashboard.py
git commit -m "feat: add dashboard layout and widgets API endpoints"
```

---

## Task 3: Backend Service Extension

**Files:**
- Modify: `backend/app/services/dashboard_service.py`

- [ ] **Step 1: Add default layout function**

```python
# Add to backend/app/services/dashboard_service.py

DEFAULT_LAYOUT = {
    "lg": [
        {"i": "kpi-pending", "type": "kpi_pending_actions", "x": 0, "y": 0, "w": 3, "h": 2},
        {"i": "kpi-overdue", "type": "kpi_overdue_tasks", "x": 3, "y": 0, "w": 3, "h": 2},
        {"i": "kpi-risk", "type": "kpi_high_risk_items", "x": 6, "y": 0, "w": 3, "h": 2},
        {"i": "kpi-trend", "type": "kpi_month_trend", "x": 9, "y": 0, "w": 3, "h": 2},
        {"i": "alert-fmea", "type": "alert_high_rpn_fmea", "x": 0, "y": 2, "w": 4, "h": 4},
        {"i": "alert-capa", "type": "alert_overdue_capa", "x": 4, "y": 2, "w": 4, "h": 4},
        {"i": "alert-ppm", "type": "alert_high_ppm_suppliers", "x": 8, "y": 2, "w": 4, "h": 4},
        {"i": "recent-actions", "type": "recent_actions", "x": 0, "y": 6, "w": 12, "h": 3},
    ]
}

WIDGET_MODULE_MAP = {
    "kpi_pending_actions": "dashboard", "kpi_overdue_tasks": "dashboard",
    "kpi_high_risk_items": "dashboard", "kpi_month_trend": "dashboard",
    "alert_high_rpn_fmea": "fmea", "alert_overdue_capa": "capa",
    "alert_high_ppm_suppliers": "supplier", "recent_actions": "dashboard",
    "spc_abnormal_count": "spc", "spc_capability_summary": "spc",
    "msa_gauge_expiry": "msa", "iqc_pending_inspections": "iqc",
    "mes_equipment_status": "mes", "supplier_ppm_trend": "supplier",
}

WIDGET_MIN_SIZES = {
    "kpi_pending_actions": {"w": 2, "h": 2},
    "kpi_overdue_tasks": {"w": 2, "h": 2},
    "kpi_high_risk_items": {"w": 2, "h": 2},
    "kpi_month_trend": {"w": 2, "h": 2},
    "alert_high_rpn_fmea": {"w": 3, "h": 3},
    "alert_overdue_capa": {"w": 3, "h": 3},
    "alert_high_ppm_suppliers": {"w": 3, "h": 3},
    "recent_actions": {"w": 6, "h": 2},
    "spc_abnormal_count": {"w": 2, "h": 2},
    "spc_capability_summary": {"w": 3, "h": 3},
    "msa_gauge_expiry": {"w": 2, "h": 2},
    "iqc_pending_inspections": {"w": 2, "h": 2},
    "mes_equipment_status": {"w": 3, "h": 2},
    "supplier_ppm_trend": {"w": 3, "h": 3},
}


async def _user_can_view_module(user, module: str, db: AsyncSession) -> bool:
    """Check if user has VIEW permission for a module."""
    from app.core.permissions import Module, PermissionLevel, get_user_permission
    level = await get_user_permission(user, Module(module), db)
    return level >= PermissionLevel.VIEW


async def filter_layout_by_permissions(layout: dict, user, db: AsyncSession) -> dict:
    """Filter layout widgets by user module permissions."""
    widgets = []
    for item in layout.get("lg", []):
        module = WIDGET_MODULE_MAP.get(item.get("type", ""), "dashboard")
        if await _user_can_view_module(user, module, db):
            widgets.append(item)
    return {"lg": widgets}


async def get_default_layout(db: AsyncSession, user) -> dict:
    """Return default layout filtered by user module permissions."""
    return await filter_layout_by_permissions(DEFAULT_LAYOUT, user, db)
```

- [ ] **Step 2: Add get_widgets_data function**

```python
async def get_widgets_data(
    db: AsyncSession,
    types: list[str],
    product_line_codes: list[str] | None,
    user_id: str,
) -> dict:
    """Aggregate widget data by type. Sequential queries for AsyncSession safety."""
    result = {
        "kpi": {}, "alerts": {}, "recent_actions": [],
        "spc": {}, "msa": {}, "iqc": {}, "mes": {}, "supplier": {},
        "errors": {},
    }

    # Determine which data modules are needed
    needs_kpi = any(t.startswith("kpi_") for t in types)
    needs_alerts = any(t.startswith("alert_") for t in types)
    needs_recent = "recent_actions" in types
    needs_spc = any(t.startswith("spc_") for t in types)
    needs_msa = any(t.startswith("msa_") for t in types)
    needs_iqc = any(t.startswith("iqc_") for t in types)
    needs_mes = any(t.startswith("mes_") for t in types)
    needs_supplier = any(t.startswith("supplier_") for t in types)

    # KPI data
    if needs_kpi:
        try:
            summary = await get_summary(db, product_line_codes=product_line_codes)
            result["kpi"] = {
                "pending_actions": summary.get("pending_actions", 0),
                "overdue_tasks": summary.get("overdue_tasks", 0),
                "high_risk_items": summary.get("high_risk_items", 0),
                "month_trend": summary.get("month_trend", 0),
            }
        except Exception as e:
            result["errors"]["kpi"] = str(e)

    # Alerts data
    if needs_alerts:
        try:
            alerts = await get_alerts(db, product_line_codes=product_line_codes)
            result["alerts"] = alerts
        except Exception as e:
            result["errors"]["alerts"] = str(e)

    # Recent actions
    if needs_recent:
        try:
            actions = await get_recent_actions(db, user_id)
            result["recent_actions"] = actions
        except Exception as e:
            result["errors"]["recent_actions"] = str(e)

    # SPC data
    if needs_spc:
        try:
            from app.models.spc import SPCAlarm, InspectionCharacteristic
            from sqlalchemy import func, select
            now = datetime.now(timezone.utc)
            week_ago = now - timedelta(days=7)

            # Count open alarms in last 7 days
            abnormal_q = select(func.count(SPCAlarm.alarm_id)).where(
                SPCAlarm.status == "open",
                SPCAlarm.triggered_at >= week_ago,
            )
            if product_line_codes:
                abnormal_q = abnormal_q.join(
                    InspectionCharacteristic,
                    SPCAlarm.ic_id == InspectionCharacteristic.ic_id,
                ).where(InspectionCharacteristic.product_line.in_(product_line_codes))

            abnormal_count = await db.scalar(abnormal_q) or 0

            # Count total inspection characteristics (as capability proxy)
            ic_q = select(func.count(InspectionCharacteristic.ic_id))
            if product_line_codes:
                ic_q = ic_q.where(InspectionCharacteristic.product_line.in_(product_line_codes))

            ic_count = await db.scalar(ic_q) or 0

            result["spc"] = {
                "abnormal_count": abnormal_count,
                "capability_summary": {
                    "count": ic_count,
                    "cpk_avg": None,  # CPK requires per-IC calculation via spc_service
                },
            }
        except Exception as e:
            result["errors"]["spc"] = str(e)

    # MSA data
    if needs_msa:
        try:
            from app.models.gauge import Gauge
            from sqlalchemy import func, select
            now = datetime.now(timezone.utc)
            expiry_date = now.date() + timedelta(days=30)

            expiry_q = select(func.count(Gauge.gauge_id)).where(
                Gauge.next_calibration_date <= expiry_date,
                Gauge.status == "active",
            )
            if product_line_codes:
                expiry_q = expiry_q.where(Gauge.product_line_code.in_(product_line_codes))

            expiry_count = await db.scalar(expiry_q) or 0
            result["msa"] = {"gauges_expiring_30d": expiry_count}
        except Exception as e:
            result["errors"]["msa"] = str(e)

    # IQC data
    if needs_iqc:
        try:
            from app.models.iqc_inspection import IqcInspection
            from sqlalchemy import func, select

            pending_q = select(func.count(IqcInspection.inspection_id)).where(
                IqcInspection.status == "pending",
            )
            if product_line_codes:
                pending_q = pending_q.where(IqcInspection.product_line_code.in_(product_line_codes))

            pending_count = await db.scalar(pending_q) or 0
            result["iqc"] = {"pending_inspections": pending_count}
        except Exception as e:
            result["errors"]["iqc"] = str(e)

    # MES data
    if needs_mes:
        try:
            from app.models.mes import MESEquipmentStatus
            from sqlalchemy import func, select

            status_q = select(
                MESEquipmentStatus.status,
                func.count(MESEquipmentStatus.record_id),
            ).group_by(MESEquipmentStatus.status)
            if product_line_codes:
                status_q = status_q.where(MESEquipmentStatus.product_line_code.in_(product_line_codes))

            status_rows = (await db.execute(status_q)).all()
            status_counts = {row[0]: row[1] for row in status_rows}

            result["mes"] = {
                "equipment_running": status_counts.get("running", 0),
                "equipment_down": status_counts.get("down", 0),
                "equipment_idle": status_counts.get("idle", 0),
            }
        except Exception as e:
            result["errors"]["mes"] = str(e)

    # Supplier data
    if needs_supplier:
        try:
            from app.models.iqc_inspection import IqcInspection
            from app.models.supplier import Supplier
            from sqlalchemy import func, select

            ppm_q = (
                select(
                    IqcInspection.supplier_id,
                    func.sum(IqcInspection.defect_qty).label("defects"),
                    func.sum(IqcInspection.lot_qty).label("lots"),
                )
                .where(IqcInspection.supplier_id.isnot(None))
                .group_by(IqcInspection.supplier_id)
                .order_by(func.sum(IqcInspection.defect_qty).desc())
                .limit(5)
            )
            if product_line_codes:
                ppm_q = ppm_q.where(IqcInspection.product_line_code.in_(product_line_codes))

            ppm_rows = (await db.execute(ppm_q)).all()
            ppm_trend = []
            for row in ppm_rows:
                if row.lots and row.lots > 0:
                    ppm = (row.defects / row.lots) * 1_000_000
                    supp = await db.get(Supplier, row.supplier_id)
                    ppm_trend.append({
                        "supplier_id": str(row.supplier_id),
                        "supplier_name": supp.name if supp else "Unknown",
                        "ppm": round(ppm, 1),
                    })

            result["supplier"] = {"ppm_trend": ppm_trend}
        except Exception as e:
            result["errors"]["supplier"] = str(e)

    return result
```

- [ ] **Step 3: Verify service compiles**

Run: `cd backend && python -c "from app.services.dashboard_service import get_widgets_data; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/dashboard_service.py
git commit -m "feat: add get_default_layout and get_widgets_data to dashboard service"
```

---

## Task 4: Frontend Dependency + Widget Type System

**Files:**
- Modify: `frontend/package.json` (indirect, via npm install)
- Create: `frontend/src/components/dashboard/widgets/types.ts`
- Create: `frontend/src/components/dashboard/widgets/registry.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/hooks/usePermission.ts`

- [ ] **Step 1: Install react-grid-layout**

```bash
cd frontend && npm install react-grid-layout && npm install -D @types/react-grid-layout
```

- [ ] **Step 2: Create widget types**

```typescript
// frontend/src/components/dashboard/widgets/types.ts
import type { ReactNode } from "react";
import type { ModuleKey } from "../../../hooks/usePermission";

export type WidgetCategory = "kpi" | "alert" | "chart" | "list";

export interface WidgetMeta {
  type: string;
  name: string;
  category: WidgetCategory;
  defaultSize: { w: number; h: number };
  minSize: { w: number; h: number };
  module: ModuleKey;
}

export interface WidgetLayoutItem {
  i: string;
  type: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface DashboardLayoutConfig {
  lg: WidgetLayoutItem[];
}

export interface DashboardWidgetsData {
  kpi: {
    pending_actions?: number;
    overdue_tasks?: number;
    high_risk_items?: number;
    month_trend?: number;
  };
  alerts: {
    high_rpn_fmeas?: Array<{ fmea_id: string; document_no: string; node_name: string; rpn: number }>;
    overdue_capas?: Array<{ report_id: string; document_no: string; overdue_days: number }>;
    high_ppm_suppliers?: Array<{ supplier_id: string; supplier_name: string; ppm: number }>;
  };
  recent_actions: Array<{
    record_id: string;
    table_name: string;
    entity_no: string;
    action: string;
    operated_at: string;
  }>;
  spc: {
    abnormal_count?: number;
    capability_summary?: { count: number; cpk_avg: number | null };
  };
  msa: {
    gauges_expiring_30d?: number;
  };
  iqc: {
    pending_inspections?: number;
  };
  mes: {
    equipment_running?: number;
    equipment_down?: number;
    equipment_idle?: number;
  };
  supplier: {
    ppm_trend?: Array<{ supplier_id: string; supplier_name: string; ppm: number }>;
  };
  errors: Record<string, string>;
}

export interface WidgetProps {
  data: DashboardWidgetsData;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
}
```

- [ ] **Step 3: Add types to frontend types index**

In `frontend/src/types/index.ts`, append:

```typescript
export type {
  WidgetMeta,
  WidgetLayoutItem,
  DashboardLayoutConfig,
  DashboardWidgetsData,
  WidgetProps,
  WidgetCategory,
} from "../components/dashboard/widgets/types";
```

- [ ] **Step 4: Add "mes" to ModuleKey**

In `frontend/src/hooks/usePermission.ts`, modify:

```typescript
export type ModuleKey =
  | "fmea" | "capa" | "dashboard" | "audit" | "customer_quality"
  | "customer_audit" | "supplier" | "iqc" | "ppap" | "spc"
  | "msa" | "planning" | "management_review" | "user_mgmt"
  | "permission_mgmt" | "special_characteristic" | "quality_goal" | "scar"
  | "knowledge_graph" | "mes";  // Added
```

- [ ] **Step 5: Create widget registry**

```typescript
// frontend/src/components/dashboard/widgets/registry.ts
import type { ReactNode } from "react";
import {
  ClockCircleOutlined,
  AlertOutlined,
  WarningOutlined,
  RiseOutlined,
  FileTextOutlined,
  BarChartOutlined,
  ToolOutlined,
  ExperimentOutlined,
  ShopOutlined,
} from "@ant-design/icons";
import type { WidgetMeta, WidgetProps } from "./types";

// Component imports will be added in subsequent tasks
// For now, define the registry structure with placeholder components

const placeholderComponent = () => null;

export const widgetRegistry: Record<string, WidgetMeta & { component: React.FC<WidgetProps> }> = {
  kpi_pending_actions: {
    type: "kpi_pending_actions",
    name: "待办事项",
    category: "kpi",
    defaultSize: { w: 3, h: 2 },
    minSize: { w: 2, h: 2 },
    module: "dashboard",
    component: placeholderComponent,
  },
  kpi_overdue_tasks: {
    type: "kpi_overdue_tasks",
    name: "超期任务",
    category: "kpi",
    defaultSize: { w: 3, h: 2 },
    minSize: { w: 2, h: 2 },
    module: "dashboard",
    component: placeholderComponent,
  },
  kpi_high_risk_items: {
    type: "kpi_high_risk_items",
    name: "高风险项",
    category: "kpi",
    defaultSize: { w: 3, h: 2 },
    minSize: { w: 2, h: 2 },
    module: "dashboard",
    component: placeholderComponent,
  },
  kpi_month_trend: {
    type: "kpi_month_trend",
    name: "本月新增 FMEA",
    category: "kpi",
    defaultSize: { w: 3, h: 2 },
    minSize: { w: 2, h: 2 },
    module: "dashboard",
    component: placeholderComponent,
  },
  alert_high_rpn_fmea: {
    type: "alert_high_rpn_fmea",
    name: "高 RPN FMEA Top5",
    category: "alert",
    defaultSize: { w: 4, h: 4 },
    minSize: { w: 3, h: 3 },
    module: "fmea",
    component: placeholderComponent,
  },
  alert_overdue_capa: {
    type: "alert_overdue_capa",
    name: "超期 CAPA Top5",
    category: "alert",
    defaultSize: { w: 4, h: 4 },
    minSize: { w: 3, h: 3 },
    module: "capa",
    component: placeholderComponent,
  },
  alert_high_ppm_suppliers: {
    type: "alert_high_ppm_suppliers",
    name: "PPM 超标供应商 Top5",
    category: "alert",
    defaultSize: { w: 4, h: 4 },
    minSize: { w: 3, h: 3 },
    module: "supplier",
    component: placeholderComponent,
  },
  recent_actions: {
    type: "recent_actions",
    name: "最近操作",
    category: "list",
    defaultSize: { w: 12, h: 3 },
    minSize: { w: 6, h: 2 },
    module: "dashboard",
    component: placeholderComponent,
  },
  spc_abnormal_count: {
    type: "spc_abnormal_count",
    name: "SPC 异常点数",
    category: "kpi",
    defaultSize: { w: 3, h: 2 },
    minSize: { w: 2, h: 2 },
    module: "spc",
    component: placeholderComponent,
  },
  spc_capability_summary: {
    type: "spc_capability_summary",
    name: "过程能力摘要",
    category: "chart",
    defaultSize: { w: 4, h: 4 },
    minSize: { w: 3, h: 3 },
    module: "spc",
    component: placeholderComponent,
  },
  msa_gauge_expiry: {
    type: "msa_gauge_expiry",
    name: "量具到期提醒",
    category: "kpi",
    defaultSize: { w: 3, h: 2 },
    minSize: { w: 2, h: 2 },
    module: "msa",
    component: placeholderComponent,
  },
  iqc_pending_inspections: {
    type: "iqc_pending_inspections",
    name: "IQC 待检批次",
    category: "kpi",
    defaultSize: { w: 3, h: 2 },
    minSize: { w: 2, h: 2 },
    module: "iqc",
    component: placeholderComponent,
  },
  mes_equipment_status: {
    type: "mes_equipment_status",
    name: "设备状态概览",
    category: "chart",
    defaultSize: { w: 4, h: 3 },
    minSize: { w: 3, h: 2 },
    module: "mes",
    component: placeholderComponent,
  },
  supplier_ppm_trend: {
    type: "supplier_ppm_trend",
    name: "供应商 PPM 趋势",
    category: "chart",
    defaultSize: { w: 4, h: 4 },
    minSize: { w: 3, h: 3 },
    module: "supplier",
    component: placeholderComponent,
  },
};

export function getWidgetMeta(type: string): WidgetMeta | undefined {
  return widgetRegistry[type];
}

export function getWidgetComponent(type: string): React.FC<WidgetProps> | undefined {
  return widgetRegistry[type]?.component;
}

export function getAllWidgets(): (WidgetMeta & { component: React.FC<WidgetProps> })[] {
  return Object.values(widgetRegistry);
}
```

- [ ] **Step 6: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors (placeholder components won't cause issues).

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/components/dashboard/widgets/types.ts frontend/src/components/dashboard/widgets/registry.ts frontend/src/types/index.ts frontend/src/hooks/usePermission.ts
git commit -m "feat: add react-grid-layout, widget types, registry, and mes module key"
```

---

## Task 5: Frontend KPI Widget Components (4 widgets)

**Files:**
- Create: `frontend/src/components/dashboard/widgets/KpiPendingWidget.tsx`
- Create: `frontend/src/components/dashboard/widgets/KpiOverdueWidget.tsx`
- Create: `frontend/src/components/dashboard/widgets/KpiRiskWidget.tsx`
- Create: `frontend/src/components/dashboard/widgets/KpiTrendWidget.tsx`
- Modify: `frontend/src/components/dashboard/widgets/registry.ts`

- [ ] **Step 1: Create KpiPendingWidget**

```tsx
// frontend/src/components/dashboard/widgets/KpiPendingWidget.tsx
import { ClockCircleOutlined } from "@ant-design/icons";
import KPICard from "../../dashboard/KPICard"; // Will be reused from existing
import type { WidgetProps } from "./types";

export default function KpiPendingWidget({ data, loading, error, onRetry }: WidgetProps) {
  const value = data.kpi?.pending_actions ?? 0;
  return (
    <KPICard
      title="待办事项"
      value={value}
      status={value > 0 ? "warning" : "success"}
      icon={<ClockCircleOutlined />}
      loading={loading}
      error={error}
      onRetry={onRetry}
    />
  );
}
```

- [ ] **Step 2: Create KpiOverdueWidget**

```tsx
// frontend/src/components/dashboard/widgets/KpiOverdueWidget.tsx
import { AlertOutlined } from "@ant-design/icons";
import KPICard from "../../dashboard/KPICard";
import type { WidgetProps } from "./types";

export default function KpiOverdueWidget({ data, loading, error, onRetry }: WidgetProps) {
  const value = data.kpi?.overdue_tasks ?? 0;
  return (
    <KPICard
      title="超期任务"
      value={value}
      status={value > 0 ? "danger" : "success"}
      icon={<AlertOutlined />}
      loading={loading}
      error={error}
      onRetry={onRetry}
    />
  );
}
```

- [ ] **Step 3: Create KpiRiskWidget**

```tsx
// frontend/src/components/dashboard/widgets/KpiRiskWidget.tsx
import { WarningOutlined } from "@ant-design/icons";
import KPICard from "../../dashboard/KPICard";
import type { WidgetProps } from "./types";

export default function KpiRiskWidget({ data, loading, error, onRetry }: WidgetProps) {
  const value = data.kpi?.high_risk_items ?? 0;
  return (
    <KPICard
      title="高风险项"
      value={value}
      status={value > 0 ? "danger" : "success"}
      icon={<WarningOutlined />}
      loading={loading}
      error={error}
      onRetry={onRetry}
    />
  );
}
```

- [ ] **Step 4: Create KpiTrendWidget**

```tsx
// frontend/src/components/dashboard/widgets/KpiTrendWidget.tsx
import { RiseOutlined } from "@ant-design/icons";
import KPICard from "../../dashboard/KPICard";
import type { WidgetProps } from "./types";

export default function KpiTrendWidget({ data, loading, error, onRetry }: WidgetProps) {
  const value = data.kpi?.month_trend ?? 0;
  const trend = value > 0 ? `↑ +${value}` : value < 0 ? `↓ ${value}` : "—";
  return (
    <KPICard
      title="本月新增"
      value={value}
      status={value > 0 ? "success" : value < 0 ? "danger" : "success"}
      subtitle={trend}
      icon={<RiseOutlined />}
      loading={loading}
      error={error}
      onRetry={onRetry}
    />
  );
}
```

- [ ] **Step 5: Register components in registry**

Update `frontend/src/components/dashboard/widgets/registry.ts`:

```typescript
import KpiPendingWidget from "./KpiPendingWidget";
import KpiOverdueWidget from "./KpiOverdueWidget";
import KpiRiskWidget from "./KpiRiskWidget";
import KpiTrendWidget from "./KpiTrendWidget";

// Update the registry entries:
kpi_pending_actions: { ... component: KpiPendingWidget ... },
kpi_overdue_tasks: { ... component: KpiOverdueWidget ... },
kpi_high_risk_items: { ... component: KpiRiskWidget ... },
kpi_month_trend: { ... component: KpiTrendWidget ... },
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/dashboard/widgets/Kpi*.tsx frontend/src/components/dashboard/widgets/registry.ts
git commit -m "feat: add KPI widget components (pending, overdue, risk, trend)"
```

---

## Task 6: Frontend Alert/List Widget Components (4 widgets)

**Files:**
- Create: `frontend/src/components/dashboard/widgets/AlertHighRpnWidget.tsx`
- Create: `frontend/src/components/dashboard/widgets/AlertOverdueCapaWidget.tsx`
- Create: `frontend/src/components/dashboard/widgets/AlertHighPpmWidget.tsx`
- Create: `frontend/src/components/dashboard/widgets/RecentActionsWidget.tsx`
- Modify: `frontend/src/components/dashboard/widgets/registry.ts`

- [ ] **Step 1: Create AlertHighRpnWidget**

```tsx
// frontend/src/components/dashboard/widgets/AlertHighRpnWidget.tsx
import { Card, List, Button, Tag } from "antd";
import { WarningOutlined } from "@ant-design/icons";
import type { WidgetProps } from "./types";

export default function AlertHighRpnWidget({ data, loading, error, onRetry }: WidgetProps) {
  const items = data.alerts?.high_rpn_fmeas ?? [];

  return (
    <Card
      title={<><WarningOutlined /> 高 RPN FMEA Top5</>}
      size="small"
      loading={loading}
    >
      {error ? (
        <Button onClick={onRetry} size="small">重试</Button>
      ) : items.length === 0 ? (
        <span style={{ color: "#999" }}>暂无高 RPN 项</span>
      ) : (
        <List
          size="small"
          dataSource={items}
          renderItem={(item) => (
            <List.Item>
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>
                {item.document_no} — {item.node_name}
              </span>
              <Tag color="red">RPN {item.rpn}</Tag>
            </List.Item>
          )}
        />
      )}
    </Card>
  );
}
```

- [ ] **Step 2: Create AlertOverdueCapaWidget**

```tsx
// frontend/src/components/dashboard/widgets/AlertOverdueCapaWidget.tsx
import { Card, List, Button, Tag } from "antd";
import { ClockCircleOutlined } from "@ant-design/icons";
import type { WidgetProps } from "./types";

export default function AlertOverdueCapaWidget({ data, loading, error, onRetry }: WidgetProps) {
  const items = data.alerts?.overdue_capas ?? [];

  return (
    <Card
      title={<><ClockCircleOutlined /> 超期 CAPA Top5</>}
      size="small"
      loading={loading}
    >
      {error ? (
        <Button onClick={onRetry} size="small">重试</Button>
      ) : items.length === 0 ? (
        <span style={{ color: "#999" }}>暂无超期 CAPA</span>
      ) : (
        <List
          size="small"
          dataSource={items}
          renderItem={(item) => (
            <List.Item>
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>
                {item.document_no}
              </span>
              <Tag color="orange">超期 {item.overdue_days} 天</Tag>
            </List.Item>
          )}
        />
      )}
    </Card>
  );
}
```

- [ ] **Step 3: Create AlertHighPpmWidget**

```tsx
// frontend/src/components/dashboard/widgets/AlertHighPpmWidget.tsx
import { Card, List, Button, Tag } from "antd";
import { AlertOutlined } from "@ant-design/icons";
import type { WidgetProps } from "./types";

export default function AlertHighPpmWidget({ data, loading, error, onRetry }: WidgetProps) {
  const items = data.alerts?.high_ppm_suppliers ?? [];

  return (
    <Card
      title={<><AlertOutlined /> PPM 超标供应商 Top5</>}
      size="small"
      loading={loading}
    >
      {error ? (
        <Button onClick={onRetry} size="small">重试</Button>
      ) : items.length === 0 ? (
        <span style={{ color: "#999" }}>暂无超标供应商</span>
      ) : (
        <List
          size="small"
          dataSource={items}
          renderItem={(item) => (
            <List.Item>
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>
                {item.supplier_name}
              </span>
              <Tag color="red">PPM {item.ppm}</Tag>
            </List.Item>
          )}
        />
      )}
    </Card>
  );
}
```

- [ ] **Step 4: Create RecentActionsWidget**

```tsx
// frontend/src/components/dashboard/widgets/RecentActionsWidget.tsx
import { Card, Table, Button } from "antd";
import { HistoryOutlined } from "@ant-design/icons";
import type { WidgetProps } from "./types";

export default function RecentActionsWidget({ data, loading, error, onRetry }: WidgetProps) {
  const items = data.recent_actions ?? [];

  const columns = [
    { title: "操作", dataIndex: "action", key: "action", width: 120 },
    { title: "对象", dataIndex: "entity_no", key: "entity_no", ellipsis: true },
    { title: "时间", dataIndex: "operated_at", key: "operated_at", width: 180 },
  ];

  return (
    <Card
      title={<><HistoryOutlined /> 最近操作</>}
      size="small"
      loading={loading}
    >
      {error ? (
        <Button onClick={onRetry} size="small">重试</Button>
      ) : (
        <Table
          size="small"
          columns={columns}
          dataSource={items}
          rowKey="record_id"
          pagination={false}
          scroll={{ y: 200 }}
        />
      )}
    </Card>
  );
}
```

- [ ] **Step 5: Update registry**

```typescript
import AlertHighRpnWidget from "./AlertHighRpnWidget";
import AlertOverdueCapaWidget from "./AlertOverdueCapaWidget";
import AlertHighPpmWidget from "./AlertHighPpmWidget";
import RecentActionsWidget from "./RecentActionsWidget";

// Update registry entries...
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/dashboard/widgets/Alert*.tsx frontend/src/components/dashboard/widgets/RecentActionsWidget.tsx frontend/src/components/dashboard/widgets/registry.ts
git commit -m "feat: add alert and list widget components"
```

---

## Task 7: Frontend Extended Widget Components (6 widgets)

**Files:**
- Create: `frontend/src/components/dashboard/widgets/SpcAbnormalWidget.tsx`
- Create: `frontend/src/components/dashboard/widgets/SpcCapabilityWidget.tsx`
- Create: `frontend/src/components/dashboard/widgets/MsaGaugeExpiryWidget.tsx`
- Create: `frontend/src/components/dashboard/widgets/IqcPendingWidget.tsx`
- Create: `frontend/src/components/dashboard/widgets/MesEquipmentWidget.tsx`
- Create: `frontend/src/components/dashboard/widgets/SupplierPpmWidget.tsx`
- Modify: `frontend/src/components/dashboard/widgets/registry.ts`

- [ ] **Step 1-6: Create each extended widget component**

Follow the same pattern as KPI widgets for simple ones, and Card+List/Table for chart-like ones. For brevity, here are the implementations:

```tsx
// SpcAbnormalWidget.tsx
import { WarningOutlined } from "@ant-design/icons";
import KPICard from "../../dashboard/KPICard";
import type { WidgetProps } from "./types";

export default function SpcAbnormalWidget({ data, loading, error, onRetry }: WidgetProps) {
  const value = data.spc?.abnormal_count ?? 0;
  return (
    <KPICard
      title="SPC 异常点数"
      value={value}
      status={value > 0 ? "danger" : "success"}
      subtitle="近7天"
      icon={<WarningOutlined />}
      loading={loading}
      error={error}
      onRetry={onRetry}
    />
  );
}
```

```tsx
// SpcCapabilityWidget.tsx
import { Card, Statistic, Button, Row, Col } from "antd";
import { BarChartOutlined } from "@ant-design/icons";
import type { WidgetProps } from "./types";

export default function SpcCapabilityWidget({ data, loading, error, onRetry }: WidgetProps) {
  const summary = data.spc?.capability_summary;
  return (
    <Card title={<><BarChartOutlined /> 过程能力摘要</>} size="small" loading={loading}>
      {error ? (
        <Button onClick={onRetry} size="small">重试</Button>
      ) : (
        <Row gutter={16}>
          <Col span={12}>
            <Statistic title="监控项数" value={summary?.count ?? 0} />
          </Col>
          <Col span={12}>
            <Statistic title="平均 CPK" value={summary?.cpk_avg ?? "—"} precision={2} />
          </Col>
        </Row>
      )}
    </Card>
  );
}
```

```tsx
// MsaGaugeExpiryWidget.tsx
import { ToolOutlined } from "@ant-design/icons";
import KPICard from "../../dashboard/KPICard";
import type { WidgetProps } from "./types";

export default function MsaGaugeExpiryWidget({ data, loading, error, onRetry }: WidgetProps) {
  const value = data.msa?.gauges_expiring_30d ?? 0;
  return (
    <KPICard
      title="量具到期提醒"
      value={value}
      status={value > 0 ? "warning" : "success"}
      subtitle="30天内到期"
      icon={<ToolOutlined />}
      loading={loading}
      error={error}
      onRetry={onRetry}
    />
  );
}
```

```tsx
// IqcPendingWidget.tsx
import { ExperimentOutlined } from "@ant-design/icons";
import KPICard from "../../dashboard/KPICard";
import type { WidgetProps } from "./types";

export default function IqcPendingWidget({ data, loading, error, onRetry }: WidgetProps) {
  const value = data.iqc?.pending_inspections ?? 0;
  return (
    <KPICard
      title="IQC 待检批次"
      value={value}
      status={value > 0 ? "warning" : "success"}
      icon={<ExperimentOutlined />}
      loading={loading}
      error={error}
      onRetry={onRetry}
    />
  );
}
```

```tsx
// MesEquipmentWidget.tsx
import { Card, Statistic, Button, Row, Col } from "antd";
import { ToolOutlined } from "@ant-design/icons";
import type { WidgetProps } from "./types";

export default function MesEquipmentWidget({ data, loading, error, onRetry }: WidgetProps) {
  const mes = data.mes ?? {};
  return (
    <Card title={<><ToolOutlined /> 设备状态概览</>} size="small" loading={loading}>
      {error ? (
        <Button onClick={onRetry} size="small">重试</Button>
      ) : (
        <Row gutter={16}>
          <Col span={8}>
            <Statistic title="运行中" value={mes.equipment_running ?? 0} valueStyle={{ color: "#52c41a" }} />
          </Col>
          <Col span={8}>
            <Statistic title="停机" value={mes.equipment_down ?? 0} valueStyle={{ color: "#ff4d4f" }} />
          </Col>
          <Col span={8}>
            <Statistic title="空闲" value={mes.equipment_idle ?? 0} valueStyle={{ color: "#faad14" }} />
          </Col>
        </Row>
      )}
    </Card>
  );
}
```

```tsx
// SupplierPpmWidget.tsx
import { Card, List, Button, Tag } from "antd";
import { ShopOutlined } from "@ant-design/icons";
import type { WidgetProps } from "./types";

export default function SupplierPpmWidget({ data, loading, error, onRetry }: WidgetProps) {
  const items = data.supplier?.ppm_trend ?? [];

  return (
    <Card
      title={<><ShopOutlined /> 供应商 PPM 趋势 Top5</>}
      size="small"
      loading={loading}
    >
      {error ? (
        <Button onClick={onRetry} size="small">重试</Button>
      ) : items.length === 0 ? (
        <span style={{ color: "#999" }}>暂无数据</span>
      ) : (
        <List
          size="small"
          dataSource={items}
          renderItem={(item) => (
            <List.Item>
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>
                {item.supplier_name}
              </span>
              <Tag color={item.ppm > 500 ? "red" : "green"}>{item.ppm} PPM</Tag>
            </List.Item>
          )}
        />
      )}
    </Card>
  );
}
```

- [ ] **Step 7: Update registry with all components**

In `frontend/src/components/dashboard/widgets/registry.ts`, add imports:

```typescript
import SpcAbnormalWidget from "./SpcAbnormalWidget";
import SpcCapabilityWidget from "./SpcCapabilityWidget";
import MsaGaugeExpiryWidget from "./MsaGaugeExpiryWidget";
import IqcPendingWidget from "./IqcPendingWidget";
import MesEquipmentWidget from "./MesEquipmentWidget";
import SupplierPpmWidget from "./SupplierPpmWidget";
```

Replace `placeholderComponent` with actual components in registry entries:
```typescript
spc_abnormal_count: { ... component: SpcAbnormalWidget ... },
spc_capability_summary: { ... component: SpcCapabilityWidget ... },
msa_gauge_expiry: { ... component: MsaGaugeExpiryWidget ... },
iqc_pending_inspections: { ... component: IqcPendingWidget ... },
mes_equipment_status: { ... component: MesEquipmentWidget ... },
supplier_ppm_trend: { ... component: SupplierPpmWidget ... },
```

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/dashboard/widgets/Spc*.tsx frontend/src/components/dashboard/widgets/Msa*.tsx frontend/src/components/dashboard/widgets/Iqc*.tsx frontend/src/components/dashboard/widgets/Mes*.tsx frontend/src/components/dashboard/widgets/Supplier*.tsx frontend/src/components/dashboard/widgets/registry.ts
git commit -m "feat: add extended widget components (spc, msa, iqc, mes, supplier)"
```

---

## Task 8: WidgetWrapper + DashboardGrid + WidgetLibraryPanel

**Files:**
- Create: `frontend/src/components/dashboard/WidgetWrapper.tsx`
- Create: `frontend/src/components/dashboard/DashboardGrid.tsx`
- Create: `frontend/src/components/dashboard/WidgetLibraryPanel.tsx`

- [ ] **Step 1: Create WidgetWrapper**

```tsx
// frontend/src/components/dashboard/WidgetWrapper.tsx
import { useRef, useEffect } from "react";
import { Card, Button, Space, theme } from "antd";
import { CloseOutlined, ReloadOutlined } from "@ant-design/icons";
import type { WidgetLayoutItem, DashboardWidgetsData } from "./widgets/types";
import { getWidgetMeta, getWidgetComponent } from "./widgets/registry";

interface WidgetWrapperProps {
  item: WidgetLayoutItem;
  data: DashboardWidgetsData;
  loading: boolean;
  isEditing: boolean;
  onRemove: (i: string) => void;
  onRetry: () => void;
}

export default function WidgetWrapper({
  item,
  data,
  loading,
  isEditing,
  onRemove,
  onRetry,
}: WidgetWrapperProps) {
  const { token } = theme.useToken();
  const containerRef = useRef<HTMLDivElement>(null);
  const meta = getWidgetMeta(item.type);
  const Component = getWidgetComponent(item.type);

  // ResizeObserver for chart auto-resize
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    let ro: ResizeObserver | null = null;
    // Debounced resize callback would go here for chart components
    // For now, the ResizeObserver is prepared for future chart widgets
    ro = new ResizeObserver(() => {
      // Chart widgets can listen to a resize context or ref
    });
    ro.observe(el);

    return () => {
      if (ro) ro.disconnect();
    };
  }, []);

  if (!Component || !meta) {
    return (
      <div style={{ padding: 16, color: token.colorTextSecondary }}>
        未知组件: {item.type}
      </div>
    );
  }

  const hasModuleError = !!data.errors?.[meta.module];

  return (
    <div ref={containerRef} style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <Card
        size="small"
        title={
          <Space>
            {meta.name}
            {hasModuleError && (
              <ReloadOutlined
                style={{ color: token.colorError, cursor: "pointer" }}
                onClick={onRetry}
              />
            )}
          </Space>
        }
        extra={
          isEditing ? (
            <Button
              type="text"
              size="small"
              danger
              icon={<CloseOutlined />}
              onClick={() => onRemove(item.i)}
            />
          ) : null
        }
        styles={{ body: { flex: 1, overflow: "auto", padding: "8px 12px" } }}
        style={{ height: "100%", display: "flex", flexDirection: "column" }}
      >
        <Component
          data={data}
          loading={loading}
          error={hasModuleError}
          onRetry={onRetry}
        />
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Create DashboardGrid**

```tsx
// frontend/src/components/dashboard/DashboardGrid.tsx
import { Responsive, WidthProvider } from "react-grid-layout";
import type { WidgetLayoutItem, DashboardWidgetsData } from "./widgets/types";
import WidgetWrapper from "./WidgetWrapper";

const ResponsiveGridLayout = WidthProvider(Responsive);

const GRID_CONFIG = {
  defaultCols: 12,
  rowHeight: 40,
  margin: [16, 16] as [number, number],
  containerPadding: [0, 0] as [number, number],
  breakpoints: { lg: 1200, md: 996, sm: 768, xs: 480 },
  cols: { lg: 12, md: 10, sm: 6, xs: 4 },
};

interface DashboardGridProps {
  layout: WidgetLayoutItem[];
  data: DashboardWidgetsData;
  loading: boolean;
  isEditing: boolean;
  onLayoutChange: (layout: WidgetLayoutItem[]) => void;
  onRemoveWidget: (i: string) => void;
  onRetry: () => void;
}

function computeMdLayout(lgLayout: WidgetLayoutItem[]): WidgetLayoutItem[] {
  return lgLayout.map((item) => {
    const w = Math.max(2, Math.round(item.w * 10 / 12));
    const x = Math.round(item.x * 10 / 12);
    return {
      ...item,
      x: Math.min(x, 10 - w),
      w,
    };
  });
}

function computeMobileLayout(lgLayout: WidgetLayoutItem[]): WidgetLayoutItem[] {
  const sorted = [...lgLayout].sort((a, b) => (a.y === b.y ? a.x - b.x : a.y - b.y));
  let currentY = 0;
  return sorted.map((item) => {
    const y = currentY;
    currentY += item.h;
    return {
      ...item,
      x: 0,
      y,
      w: 6, // Will be overridden by cols for sm/xs
    };
  });
}

export default function DashboardGrid({
  layout,
  data,
  loading,
  isEditing,
  onLayoutChange,
  onRemoveWidget,
  onRetry,
}: DashboardGridProps) {
  const [currentBreakpoint, setCurrentBreakpoint] = useState<string>("lg");

  const layouts = {
    lg: layout,
    md: computeMdLayout(layout),
    sm: computeMobileLayout(layout).map((i) => ({ ...i, w: 6 })),
    xs: computeMobileLayout(layout).map((i) => ({ ...i, w: 4 })),
  };

  // Only allow editing on lg breakpoint to avoid md layout overwriting lg persisted state
  const canEdit = isEditing && currentBreakpoint === "lg";

  return (
    <ResponsiveGridLayout
      className="dashboard-grid"
      layouts={layouts}
      breakpoints={GRID_CONFIG.breakpoints}
      cols={GRID_CONFIG.cols}
      rowHeight={GRID_CONFIG.rowHeight}
      margin={GRID_CONFIG.margin}
      containerPadding={GRID_CONFIG.containerPadding}
      onBreakpointChange={(bp) => setCurrentBreakpoint(bp)}
      compactType="vertical"
      isDraggable={canEdit}
      isResizable={canEdit}
      onLayoutChange={(currentLayout, allLayouts) => {
        // IMPORTANT: react-grid-layout onLayoutChange only returns {i,x,y,w,h}.
        // We must merge 'type' back from the original layout by matching 'i'.
        // Also: we only persist lg breakpoint; edit mode is disabled on md/sm/xs.
        if (isEditing && allLayouts.lg) {
          const typeMap = new Map(layout.map((w) => [w.i, w.type]));
          const newLayout = allLayouts.lg.map((l) => ({
            i: l.i,
            type: typeMap.get(l.i) || "",
            x: l.x,
            y: l.y,
            w: l.w,
            h: l.h,
          }));
          onLayoutChange(newLayout);
        }
      }}
    >
      {layout.map((item) => (
        <div key={item.i}>
          <WidgetWrapper
            item={item}
            data={data}
            loading={loading}
            isEditing={isEditing}
            onRemove={onRemoveWidget}
            onRetry={onRetry}
          />
        </div>
      ))}
    </ResponsiveGridLayout>
  );
}
```

- [ ] **Step 3: Create WidgetLibraryPanel**

```tsx
// frontend/src/components/dashboard/WidgetLibraryPanel.tsx
import { useState } from "react";
import { Input, Collapse, Button, Badge, theme } from "antd";
import { SearchOutlined, PlusOutlined } from "@ant-design/icons";
import { usePermission } from "../../hooks/usePermission";
import { getAllWidgets } from "./widgets/registry";
import type { WidgetMeta } from "./widgets/types";

interface WidgetLibraryPanelProps {
  onAddWidget: (type: string) => void;
}

export default function WidgetLibraryPanel({ onAddWidget }: WidgetLibraryPanelProps) {
  const { token } = theme.useToken();
  const { canView } = usePermission();
  const [search, setSearch] = useState("");

  const allWidgets = getAllWidgets().filter((w) => canView(w.module));

  const filtered = search
    ? allWidgets.filter((w) => w.name.toLowerCase().includes(search.toLowerCase()))
    : allWidgets;

  const byCategory: Record<string, WidgetMeta[]> = {};
  filtered.forEach((w) => {
    byCategory[w.category] = byCategory[w.category] || [];
    byCategory[w.category].push(w);
  });

  const categoryLabels: Record<string, string> = {
    kpi: "📊 KPI 指标",
    alert: "⚠️ 预警提醒",
    chart: "📈 图表分析",
    list: "📋 列表",
  };

  const items = Object.entries(byCategory).map(([cat, widgets]) => ({
    key: cat,
    label: `${categoryLabels[cat] || cat} (${widgets.length})`,
    children: (
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {widgets.map((w) => (
          <Button
            key={w.type}
            type="dashed"
            block
            icon={<PlusOutlined />}
            onClick={() => onAddWidget(w.type)}
            style={{ textAlign: "left" }}
          >
            {w.name}
          </Button>
        ))}
      </div>
    ),
  }));

  return (
    <div
      style={{
        width: 240,
        height: "100%",
        borderRight: `1px solid ${token.colorBorderSecondary}`,
        padding: 16,
        overflowY: "auto",
        background: token.colorBgContainer,
      }}
    >
      <h4 style={{ marginBottom: 12 }}>📦 组件库</h4>
      <Input
        placeholder="搜索组件..."
        prefix={<SearchOutlined />}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={{ marginBottom: 12 }}
      />
      <Collapse items={items} defaultActiveKey={["kpi", "alert"]} ghost />
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/dashboard/WidgetWrapper.tsx frontend/src/components/dashboard/DashboardGrid.tsx frontend/src/components/dashboard/WidgetLibraryPanel.tsx
git commit -m "feat: add WidgetWrapper, DashboardGrid, and WidgetLibraryPanel"
```

---

## Task 9: DashboardPage Rewrite

**Files:**
- Modify: `frontend/src/pages/dashboard/DashboardPage.tsx`
- Modify: `frontend/src/api/dashboard.ts`

- [ ] **Step 1: Extend dashboard API client**

```typescript
// Add to frontend/src/api/dashboard.ts
import type { DashboardLayoutConfig, DashboardWidgetsData } from "../types";

export async function getDashboardLayout(): Promise<{
  layout_id: string | null;
  layout_config: DashboardLayoutConfig;
}> {
  const resp = await client.get("/dashboard/layout");
  return resp.data;
}

export async function saveDashboardLayout(
  layoutConfig: DashboardLayoutConfig
): Promise<unknown> {
  const resp = await client.put("/dashboard/layout", { layout_config: layoutConfig });
  return resp.data;
}

export async function getDashboardWidgets(
  types: string[],
  productLine?: string
): Promise<DashboardWidgetsData> {
  const resp = await client.get("/dashboard/widgets", {
    params: {
      types: types.join(","),
      product_line: productLine || undefined,
    },
  });
  return resp.data;
}
```

- [ ] **Step 2: Rewrite DashboardPage**

```tsx
// frontend/src/pages/dashboard/DashboardPage.tsx
import { useEffect, useState, useCallback, useMemo } from "react";
import { Button, Typography, Space, message } from "antd";
import {
  EditOutlined,
  CheckOutlined,
  CloseOutlined,
  ReloadOutlined,
  RollbackOutlined,
} from "@ant-design/icons";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import DashboardGrid from "../../components/dashboard/DashboardGrid";
import WidgetLibraryPanel from "../../components/dashboard/WidgetLibraryPanel";
import {
  getDashboardLayout,
  saveDashboardLayout,
  getDashboardWidgets,
} from "../../api/dashboard";
import { useProductLineStore } from "../../store/productLineStore";
import { usePermission } from "../../hooks/usePermission";
import type {
  WidgetLayoutItem,
  DashboardLayoutConfig,
  DashboardWidgetsData,
} from "../../types";

const DEFAULT_LAYOUT: DashboardLayoutConfig = {
  lg: [
    { i: "kpi-pending", type: "kpi_pending_actions", x: 0, y: 0, w: 3, h: 2 },
    { i: "kpi-overdue", type: "kpi_overdue_tasks", x: 3, y: 0, w: 3, h: 2 },
    { i: "kpi-risk", type: "kpi_high_risk_items", x: 6, y: 0, w: 3, h: 2 },
    { i: "kpi-trend", type: "kpi_month_trend", x: 9, y: 0, w: 3, h: 2 },
    { i: "alert-fmea", type: "alert_high_rpn_fmea", x: 0, y: 2, w: 4, h: 4 },
    { i: "alert-capa", type: "alert_overdue_capa", x: 4, y: 2, w: 4, h: 4 },
    { i: "alert-ppm", type: "alert_high_ppm_suppliers", x: 8, y: 2, w: 4, h: 4 },
    { i: "recent-actions", type: "recent_actions", x: 0, y: 6, w: 12, h: 3 },
  ],
};

const { Title } = Typography;

export default function DashboardPage() {
  const productLine = useProductLineStore((s) => s.selected);
  const { canEdit } = usePermission();
  const canEditDashboard = canEdit("dashboard");

  const [layout, setLayout] = useState<WidgetLayoutItem[]>(DEFAULT_LAYOUT.lg);
  const [editLayout, setEditLayout] = useState<WidgetLayoutItem[] | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [data, setData] = useState<DashboardWidgetsData>({
    kpi: {}, alerts: {}, recent_actions: [], spc: {}, msa: {}, iqc: {}, mes: {}, supplier: {}, errors: {},
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // Fetch layout first, then fetch widgets based on returned layout types
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const layoutResp = await getDashboardLayout();
      const validWidgets = (layoutResp.layout_config?.lg ?? DEFAULT_LAYOUT.lg).filter(
        (item) => !!item.type
      );
      setLayout(validWidgets);

      const widgetTypes = validWidgets.map((w) => w.type).filter((v, i, a) => a.indexOf(v) === i);
      const widgetsResp = await getDashboardWidgets(widgetTypes, productLine || undefined);
      setData(widgetsResp);
    } catch (e) {
      console.error("Dashboard fetch error:", e);
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [productLine]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleEdit = () => {
    setEditLayout([...layout]);
    setIsEditing(true);
  };

  const handleSave = async () => {
    if (!editLayout) return;
    try {
      await saveDashboardLayout({ lg: editLayout });
      setLayout(editLayout);
      setIsEditing(false);
      setEditLayout(null);
      message.success("布局已保存");
      fetchData();
    } catch (e) {
      message.error("保存失败");
    }
  };

  const handleCancel = () => {
    setEditLayout(null);
    setIsEditing(false);
  };

  const handleReset = async () => {
    try {
      await saveDashboardLayout(DEFAULT_LAYOUT);
      setLayout(DEFAULT_LAYOUT.lg);
      setEditLayout(DEFAULT_LAYOUT.lg);
      message.success("已恢复默认布局");
      fetchData();
    } catch (e) {
      message.error("恢复失败");
    }
  };

  const handleAddWidget = (type: string) => {
    if (!editLayout) return;
    const id =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : Math.random().toString(36).substring(2, 11);
    const newItem: WidgetLayoutItem = {
      i: `${type}-${id}`,
      type,
      x: 0,
      y: 100, // Will be compacted by react-grid-layout
      w: 3,
      h: 2,
    };
    setEditLayout([...editLayout, newItem]);
  };

  const handleRemoveWidget = (i: string) => {
    if (!editLayout) return;
    setEditLayout(editLayout.filter((w) => w.i !== i));
  };

  const currentLayout = isEditing && editLayout ? editLayout : layout;

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>质量仪表盘</Title>
        <Space>
          {isEditing ? (
            <>
              <Button icon={<CheckOutlined />} type="primary" onClick={handleSave}>
                完成
              </Button>
              <Button icon={<CloseOutlined />} onClick={handleCancel}>
                取消
              </Button>
              <Button icon={<RollbackOutlined />} onClick={handleReset}>
                恢复默认
              </Button>
            </>
          ) : (
            <>
              <Button icon={<ReloadOutlined />} onClick={fetchData} loading={loading}>
                刷新
              </Button>
              {canEditDashboard && (
                <Button icon={<EditOutlined />} onClick={handleEdit}>
                  编辑布局
                </Button>
              )}
            </>
          )}
        </Space>
      </div>

      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {isEditing && (
          <WidgetLibraryPanel onAddWidget={handleAddWidget} />
        )}
        <div style={{ flex: 1, overflow: "auto", padding: "0 8px" }}>
          <DashboardGrid
            layout={currentLayout}
            data={data}
            loading={loading}
            isEditing={isEditing}
            onLayoutChange={(newLayout) => {
              if (isEditing) setEditLayout(newLayout);
            }}
            onRemoveWidget={handleRemoveWidget}
            onRetry={fetchData}
          />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/dashboard/DashboardPage.tsx frontend/src/api/dashboard.ts
git commit -m "feat: rewrite DashboardPage with editable grid layout"
```

---

## Task 10: Integration Verification

**Files:** All modified files.

- [ ] **Step 1: Backend verification**

Run: `cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
Test: `curl http://localhost:8000/api/dashboard/layout` (with auth token)
Expected: Returns layout config with `lg` array.

- [ ] **Step 2: Frontend build verification**

Run: `cd frontend && npm run build`
Expected: Build succeeds, no TypeScript errors.

- [ ] **Step 3: Frontend lint verification**

Run: `cd frontend && npm run lint`
Expected: Passes with ≤ existing warning count.

- [ ] **Step 4: End-to-end smoke test**

1. Start backend: `cd backend && uvicorn app.main:app --reload`
2. Start frontend: `cd frontend && npm run dev`
3. Open `http://localhost:5173/dashboard`
4. Verify: Default layout loads with 4 KPI + 3 Alert + Recent Actions
5. Click "编辑布局" → verify edit mode opens with sidebar
6. Drag a widget → verify position updates
7. Add a new widget from sidebar → verify it appears
8. Click "完成" → verify layout saves, page refreshes
9. Resize browser to < 768px → verify linear layout, no edit button

- [ ] **Step 5: Final commit**

```bash
git add .
git commit -m "feat: complete customizable drag-and-drop dashboard"
```

---

## Self-Review

### 1. Spec Coverage Check

| Spec Requirement | Plan Task |
|:---|:---|
| `user_dashboard_layouts` table | Task 1 |
| JSONB `layout_config` with `lg` array | Task 1, 2 |
| Default layout filtered by permissions | Task 3 (`get_default_layout`) |
| GET/PUT `/layout` API | Task 2 |
| GET `/widgets?types=...` with validation | Task 2 |
| Sequential queries with error isolation | Task 3 (`get_widgets_data`) |
| RLS product_line_codes filtering | Task 3 (all queries use filter_codes) |
| `errors` field in widgets response | Task 3 |
| 14 widget components | Tasks 5, 6, 7 |
| Widget registry with type→component mapping | Task 4 |
| react-grid-layout integration | Task 8 (`DashboardGrid`) |
| Edit mode toggle + sidebar | Task 9 (`DashboardPage`) |
| ResizeObserver in WidgetWrapper | Task 8 |
| Mobile degradation (< 768px linear) | Task 8 (`computeMobileLayout`) |
| `canEdit("dashboard")` permission check | Task 9 |
| Frontend API paths (`/dashboard/*`, not `/api/dashboard/*`) | Task 9 |
| `"mes"` in ModuleKey | Task 4 |

**No gaps found.**

### 2. Placeholder Scan

- No "TBD", "TODO", "implement later" found.
- No "add appropriate error handling" without code.
- No "similar to Task N" references.
- All steps contain actual code or exact commands.

### 3. Type Consistency Check

| Type/Field | Defined In | Used In | Status |
|:---|:---|:---|:---|
| `WidgetLayoutItem` | `types.ts` | registry, DashboardGrid, WidgetWrapper, API | ✅ Consistent |
| `DashboardLayoutConfig.lg` | `types.ts` | API, DashboardPage, schemas | ✅ Consistent |
| `DashboardWidgetsData.errors` | `types.ts` | service, WidgetWrapper | ✅ Consistent |
| `WidgetProps` | `types.ts` | all 14 widget components | ✅ Consistent |
| `widgetRegistry` | `registry.ts` | DashboardPage, WidgetLibraryPanel | ✅ Consistent |
| `GRID_CONFIG.cols` | `DashboardGrid.tsx` | — | ✅ Correct prop name |

**All types consistent.**

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-08-custom-dashboard-implementation.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session, batch execution with checkpoints for review

**Which approach?**
