# 供货质量看板实施计划 (Supplier Quality Dashboard Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a comprehensive supplier quality analytics platform with dashboard view, supplier detail drill-down, and multi-supplier comparison capabilities.

**Architecture:** Real-time aggregation from existing IQC inspections, supplier evaluations, and SCAR tables. Three-view frontend (summary → detail → compare) with @ant-design/charts visualization and Excel export.

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 (async) | React 18 + TypeScript + Ant Design 5 + @ant-design/charts | PostgreSQL 15 | openpyxl

---

## File Structure

**Backend:**
- Create: `backend/app/services/supplier_quality_service.py` — aggregation & calculation logic
- Modify: `backend/app/api/supplier.py` — mount quality sub-routes
- Modify: `backend/app/schemas/supplier.py` — add quality response schemas
- Modify: `backend/requirements.txt` — add `openpyxl` dependency

**Frontend:**
- Create: `frontend/src/pages/supplier/SupplierQualityPage.tsx` — main page with view switcher
- Create: `frontend/src/pages/supplier/components/DashboardView.tsx` — summary KPIs + trends
- Create: `frontend/src/pages/supplier/components/SupplierDetailView.tsx` — single supplier drill-down
- Create: `frontend/src/pages/supplier/components/CompareView.tsx` — multi-supplier comparison
- Modify: `frontend/src/api/supplier.ts` — add quality API client functions
- Modify: `frontend/src/types/index.ts` — add quality response types
- Modify: `frontend/src/App.tsx` — add `/suppliers/quality` route
- Modify: `frontend/src/components/layout/AppLayout.tsx` — add sidebar menu entry
- Modify: `frontend/package.json` — add `@ant-design/charts` dependency

---

## Task 1: Install Dependencies

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `frontend/package.json`

- [ ] **Step 1: Add openpyxl to backend requirements**

```diff
# backend/requirements.txt
# ... existing dependencies ...
alembic==1.13.1
annotated-types==0.6.0
# ... other dependencies ...
+openpyxl==3.1.2
```

- [ ] **Step 2: Add @ant-design/charts to frontend package.json**

```bash
cd /Users/sam/Documents/Code/OpenQMS/frontend
npm install @ant-design/charts
```

Expected: `package.json` updated with `@ant-design/charts` dependency

- [ ] **Step 3: Commit dependency changes**

```bash
git add backend/requirements.txt frontend/package.json frontend/package-lock.json
git commit -m "chore: add openpyxl and @ant-design/charts dependencies for supplier quality dashboard"
```

---

## Task 2: Define Quality Response Schemas

**Files:**
- Modify: `backend/app/schemas/supplier.py`

- [ ] **Step 1: Add quality dashboard response schemas**

Append to `backend/app/schemas/supplier.py`:

```python
# ─── Quality Dashboard ───

from datetime import date
from typing import List


class QualityKPI(BaseModel):
    total_suppliers: int
    overall_ppm: float
    batch_acceptance_rate: float
    open_scar_count: int


class PPMTrendPoint(BaseModel):
    month: str
    ppm: float


class GradeDistribution(BaseModel):
    A: int
    B: int
    C: int
    D: int


class SupplierRankingItem(BaseModel):
    supplier_id: uuid.UUID
    supplier_no: str
    name: str
    grade: str
    ppm: float
    batch_acceptance_rate: float
    delivery_rate: float
    open_scar_count: int

    model_config = {"from_attributes": True}


class QualityDashboardResponse(BaseModel):
    kpi: QualityKPI
    ppm_trend: List[PPMTrendPoint]
    grade_distribution: GradeDistribution
    ranking: List[SupplierRankingItem]


class SupplierQualityStats(BaseModel):
    grade: str
    total_score: float
    quality_score: float
    delivery_score: float
    service_score: float
    ppm: float
    batch_acceptance_rate: float
    total_inspections: int
    accepted_count: int
    scar_count: int
    open_scar_count: int


class SupplierQualityDetailResponse(BaseModel):
    supplier: SupplierResponse
    stats: SupplierQualityStats
    ppm_trend: List[PPMTrendPoint]
    acceptance_trend: List[dict]


class SupplierCompareItem(BaseModel):
    supplier_id: uuid.UUID
    name: str
    supplier_no: str
    grade: str
    ppm: float
    batch_acceptance_rate: float
    delivery_rate: float
    open_scar_count: int
    quality_score: float
    delivery_score: float
    service_score: float

    model_config = {"from_attributes": True}


class SupplierCompareResponse(BaseModel):
    suppliers: List[SupplierCompareItem]
    ppm_trends: dict
```

- [ ] **Step 2: Commit schema changes**

```bash
git add backend/app/schemas/supplier.py
git commit -m "feat(backend): add supplier quality dashboard response schemas"
```

---

## Task 3: Implement Quality Service Layer

**Files:**
- Create: `backend/app/services/supplier_quality_service.py`

- [ ] **Step 1: Create supplier_quality_service.py with aggregation functions**

```python
from datetime import datetime, date, timedelta
from typing import List, Optional
from sqlalchemy import select, func, case, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import coalesce

from app.models.supplier import Supplier, SupplierEvaluation, SupplierSCAR
from app.models.iqc_inspection import IqcInspection


async def get_quality_dashboard(
    db: AsyncSession,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    product_line_code: Optional[str] = None,
) -> dict:
    """Aggregate quality KPIs, trends, and rankings from IQC inspections and evaluations."""
    
    # Default to last 6 months if not specified
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=180)
    
    # Build base filters
    iqc_filter = [
        IqcInspection.inspection_date >= start_date,
        IqcInspection.inspection_date <= end_date,
    ]
    if product_line_code:
        iqc_filter.append(IqcInspection.product_line_code == product_line_code)
    
    # Overall PPM: (total defects / total lot quantity) * 1,000,000
    # Note: Using lot_qty as denominator (business confirmed)
    ppm_result = await db.execute(
        select(
            func.coalesce(func.sum(IqcInspection.defect_qty), 0).label("total_defects"),
            func.coalesce(func.sum(IqcInspection.lot_qty), 0).label("total_lot_qty"),
        ).where(*iqc_filter)
    )
    ppm_row = ppm_result.one()
    overall_ppm = (
        (ppm_row.total_defects / ppm_row.total_lot_qty * 1_000_000)
        if ppm_row.total_lot_qty > 0
        else 0.0
    )
    
    # Batch acceptance rate: accepted_count / total_inspections
    acceptance_result = await db.execute(
        select(
            func.count().label("total"),
            func.count(case((IqcInspection.inspection_result == "accepted", 1))).label("accepted"),
        ).where(*iqc_filter)
    )
    acc_row = acceptance_result.one()
    batch_acceptance_rate = acc_row.accepted / acc_row.total if acc_row.total > 0 else 0.0
    
    # Open SCAR count
    scar_filter = [SupplierSCAR.status == "open"]
    open_scar_result = await db.scalar(
        select(func.count()).select_from(SupplierSCAR).where(*scar_filter)
    )
    open_scar_count = open_scar_result or 0
    
    # Total suppliers
    total_suppliers = await db.scalar(select(func.count()).select_from(Supplier)) or 0
    
    # PPM trend by month (last 6 months)
    # Use database-agnostic extract() instead of DATE_TRUNC
    trend_result = await db.execute(
        select(
            func.extract("year", IqcInspection.inspection_date).label("year"),
            func.extract("month", IqcInspection.inspection_date).label("month"),
            func.coalesce(func.sum(IqcInspection.defect_qty), 0).label("defects"),
            func.coalesce(func.sum(IqcInspection.lot_qty), 0).label("lots"),
        )
        .where(*iqc_filter)
        .group_by("year", "month")
        .order_by("year", "month")
    )
    trend_rows = trend_result.all()
    ppm_trend = [
        {
            "month": f"{int(row.year)}-{int(row.month):02d}",
            "ppm": (row.defects / row.lots * 1_000_000) if row.lots > 0 else 0.0,
        }
        for row in trend_rows
    ]
    
    # Grade distribution from latest evaluations
    # Note: Cannot use MAX() on UUID field, use MAX(created_at) instead
    latest_eval_subq = (
        select(
            SupplierEvaluation.supplier_id,
            func.max(SupplierEvaluation.created_at).label("max_created_at")
        )
        .group_by(SupplierEvaluation.supplier_id)
        .subquery()
    )
    
    grade_result = await db.execute(
        select(
            SupplierEvaluation.grade,
            func.count(func.distinct(SupplierEvaluation.supplier_id)).label("count"),
        )
        .select_from(SupplierEvaluation)
        .join(
            latest_eval_subq,
            and_(
                SupplierEvaluation.supplier_id == latest_eval_subq.c.supplier_id,
                SupplierEvaluation.created_at == latest_eval_subq.c.max_created_at
            )
        )
        .group_by(SupplierEvaluation.grade)
    )
    grade_rows = grade_result.all()
    grade_distribution = {"A": 0, "B": 0, "C": 0, "D": 0}
    for row in grade_rows:
        if row.grade in grade_distribution:
            grade_distribution[row.grade] = row.count
    
    # Supplier ranking (top 20 by latest evaluation total_score)
    ranking_result = await db.execute(
        select(
            Supplier.supplier_id,
            Supplier.supplier_no,
            Supplier.name,
            SupplierEvaluation.grade,
            SupplierEvaluation.total_score,
        )
        .select_from(Supplier)
        .join(SupplierEvaluation, Supplier.supplier_id == SupplierEvaluation.supplier_id)
        .join(
            latest_eval_subq,
            and_(
                SupplierEvaluation.supplier_id == latest_eval_subq.c.supplier_id,
                SupplierEvaluation.created_at == latest_eval_subq.c.max_created_at
            )
        )
        .order_by(SupplierEvaluation.total_score.desc())
        .limit(20)
    )
    ranking_rows = ranking_result.all()
    
    # Fetch additional stats for each ranked supplier
    ranking = []
    for row in ranking_rows:
        # PPM for this supplier
        supp_ppm_result = await db.execute(
            select(
                func.coalesce(func.sum(IqcInspection.defect_qty), 0),
                func.coalesce(func.sum(IqcInspection.lot_qty), 0),
            )
            .where(IqcInspection.supplier_id == row.supplier_id, *iqc_filter[2:])
        )
        supp_ppm_row = supp_ppm_result.one()
        supp_ppm = (
            (supp_ppm_row[0] / supp_ppm_row[1] * 1_000_000)
            if supp_ppm_row[1] > 0
            else 0.0
        )
        
        # Acceptance rate
        supp_acc_result = await db.execute(
            select(
                func.count(),
                func.count(case((IqcInspection.inspection_result == "accepted", 1))),
            ).where(IqcInspection.supplier_id == row.supplier_id, *iqc_filter[2:])
        )
        supp_acc_row = supp_acc_result.one()
        supp_acc_rate = supp_acc_row[1] / supp_acc_row[0] if supp_acc_row[0] > 0 else 0.0
        
        # Open SCAR count
        supp_scar_count = await db.scalar(
            select(func.count())
            .select_from(SupplierSCAR)
            .where(SupplierSCAR.supplier_id == row.supplier_id, SupplierSCAR.status == "open")
        ) or 0
        
        # Delivery rate from evaluation (map 0-100 to 0.0-1.0)
        delivery_rate = 0.0
        if row.total_score:
            eval_result = await db.execute(
                select(SupplierEvaluation.delivery_score)
                .where(SupplierEvaluation.supplier_id == row.supplier_id)
                .order_by(SupplierEvaluation.created_at.desc())
                .limit(1)
            )
            eval_row = eval_result.first()
            if eval_row:
                delivery_rate = eval_row[0] / 100.0
        
        ranking.append({
            "supplier_id": row.supplier_id,
            "supplier_no": row.supplier_no,
            "name": row.name,
            "grade": row.grade,
            "ppm": supp_ppm,
            "batch_acceptance_rate": supp_acc_rate,
            "delivery_rate": delivery_rate,
            "open_scar_count": supp_scar_count,
        })
    
    return {
        "kpi": {
            "total_suppliers": total_suppliers,
            "overall_ppm": overall_ppm,
            "batch_acceptance_rate": batch_acceptance_rate,
            "open_scar_count": open_scar_count,
        },
        "ppm_trend": ppm_trend,
        "grade_distribution": grade_distribution,
        "ranking": ranking,
    }


async def get_supplier_quality_detail(
    db: AsyncSession,
    supplier_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> dict:
    """Get quality stats and trends for a single supplier."""
    
    from app.services.supplier_service import get_supplier
    
    supplier = await get_supplier(db, supplier_id)
    
    if not start_date:
        start_date = date.today() - timedelta(days=180)
    if not end_date:
        end_date = date.today()
    
    # Get latest evaluation (use MAX(created_at) instead of MAX(eval_id) since eval_id is UUID)
    latest_eval_subq = (
        select(
            SupplierEvaluation.supplier_id,
            func.max(SupplierEvaluation.created_at).label("max_created_at")
        )
        .where(SupplierEvaluation.supplier_id == supplier_id)
        .group_by(SupplierEvaluation.supplier_id)
        .subquery()
    )
    
    latest_eval = await db.execute(
        select(SupplierEvaluation)
        .select_from(SupplierEvaluation)
        .join(
            latest_eval_subq,
            and_(
                SupplierEvaluation.supplier_id == latest_eval_subq.c.supplier_id,
                SupplierEvaluation.created_at == latest_eval_subq.c.max_created_at
            )
        )
        .limit(1)
    )
    eval_row = latest_eval.scalar_one_or_none()
    
    # PPM and acceptance stats
    iqc_filter = [
        IqcInspection.supplier_id == supplier_id,
        IqcInspection.inspection_date >= start_date,
        IqcInspection.inspection_date <= end_date,
    ]
    
    ppm_result = await db.execute(
        select(
            func.coalesce(func.sum(IqcInspection.defect_qty), 0),
            func.coalesce(func.sum(IqcInspection.lot_qty), 0),
        ).where(*iqc_filter)
    )
    ppm_row = ppm_result.one()
    ppm = (ppm_row[0] / ppm_row[1] * 1_000_000) if ppm_row[1] > 0 else 0.0
    
    acc_result = await db.execute(
        select(
            func.count(),
            func.count(case((IqcInspection.inspection_result == "accepted", 1))),
        ).where(*iqc_filter)
    )
    acc_row = acc_result.one()
    total_inspections = acc_row[0]
    accepted_count = acc_row[1]
    batch_acceptance_rate = accepted_count / total_inspections if total_inspections > 0 else 0.0
    
    # SCAR counts
    scar_count = await db.scalar(
        select(func.count())
        .select_from(SupplierSCAR)
        .where(SupplierSCAR.supplier_id == supplier_id)
    ) or 0
    
    open_scar_count = await db.scalar(
        select(func.count())
        .select_from(SupplierSCAR)
        .where(SupplierSCAR.supplier_id == supplier_id, SupplierSCAR.status == "open")
    ) or 0
    
    # PPM trend
    trend_result = await db.execute(
        select(
            func.extract("year", IqcInspection.inspection_date),
            func.extract("month", IqcInspection.inspection_date),
            func.coalesce(func.sum(IqcInspection.defect_qty), 0),
            func.coalesce(func.sum(IqcInspection.lot_qty), 0),
        )
        .where(*iqc_filter)
        .group_by("year", "month")
        .order_by("year", "month")
    )
    trend_rows = trend_result.all()
    ppm_trend = [
        {
            "month": f"{int(row[0])}-{int(row[1]):02d}",
            "ppm": (row[2] / row[3] * 1_000_000) if row[3] > 0 else 0.0,
        }
        for row in trend_rows
    ]
    
    # Acceptance trend
    acc_trend_result = await db.execute(
        select(
            func.extract("year", IqcInspection.inspection_date),
            func.extract("month", IqcInspection.inspection_date),
            func.count(),
            func.count(case((IqcInspection.inspection_result == "accepted", 1))),
        )
        .where(*iqc_filter)
        .group_by("year", "month")
        .order_by("year", "month")
    )
    acc_trend_rows = acc_trend_result.all()
    acceptance_trend = [
        {
            "month": f"{int(row[0])}-{int(row[1]):02d}",
            "rate": row[3] / row[2] if row[2] > 0 else 0.0,
        }
        for row in acc_trend_rows
    ]
    
    return {
        "supplier": supplier,
        "stats": {
            "grade": eval_row.grade if eval_row else "N/A",
            "total_score": eval_row.total_score if eval_row else 0.0,
            "quality_score": eval_row.quality_score if eval_row else 0.0,
            "delivery_score": eval_row.delivery_score if eval_row else 0.0,
            "service_score": eval_row.service_score if eval_row else 0.0,
            "ppm": ppm,
            "batch_acceptance_rate": batch_acceptance_rate,
            "total_inspections": total_inspections,
            "accepted_count": accepted_count,
            "scar_count": scar_count,
            "open_scar_count": open_scar_count,
        },
        "ppm_trend": ppm_trend,
        "acceptance_trend": acceptance_trend,
    }


async def get_supplier_compare(
    db: AsyncSession,
    supplier_ids: List[str],
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> dict:
    """Compare multiple suppliers across quality metrics."""
    
    if not start_date:
        start_date = date.today() - timedelta(days=180)
    if not end_date:
        end_date = date.today()
    
    suppliers = []
    ppm_trends = {}
    
    for sid in supplier_ids:
        detail = await get_supplier_quality_detail(db, sid, start_date, end_date)
        
        suppliers.append({
            "supplier_id": sid,
            "name": detail["supplier"]["name"],
            "supplier_no": detail["supplier"]["supplier_no"],
            "grade": detail["stats"]["grade"],
            "ppm": detail["stats"]["ppm"],
            "batch_acceptance_rate": detail["stats"]["batch_acceptance_rate"],
            "delivery_rate": detail["stats"]["delivery_score"] / 100.0,
            "open_scar_count": detail["stats"]["open_scar_count"],
            "quality_score": detail["stats"]["quality_score"],
            "delivery_score": detail["stats"]["delivery_score"],
            "service_score": detail["stats"]["service_score"],
        })
        
        ppm_trends[sid] = detail["ppm_trend"]
    
    return {
        "suppliers": suppliers,
        "ppm_trends": ppm_trends,
    }


async def export_quality_dashboard_excel(
    db: AsyncSession,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    product_line_code: Optional[str] = None,
) -> bytes:
    """Export supplier quality dashboard data to Excel."""
    
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    
    dashboard_data = await get_quality_dashboard(db, start_date, end_date, product_line_code)
    
    wb = Workbook()
    
    # Sheet 1: Supplier ranking
    ws1 = wb.active
    ws1.title = "供应商质量排名"
    
    # Header
    headers = ["排名", "供应商编号", "供应商名称", "评级", "PPM", "批次合格率", "交付准时率", "开放SCAR"]
    ws1.append(headers)
    
    # Style header
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1677FF", end_color="1677FF", fill_type="solid")
    for cell in ws1[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    
    # Data rows
    for idx, item in enumerate(dashboard_data["ranking"], 1):
        ws1.append([
            idx,
            item["supplier_no"],
            item["name"],
            item["grade"],
            round(item["ppm"], 2),
            f"{item['batch_acceptance_rate'] * 100:.2f}%",
            f"{item['delivery_rate'] * 100:.2f}%",
            item["open_scar_count"],
        ])
    
    # Sheet 2: PPM trend
    ws2 = wb.create_sheet("PPM月度趋势")
    ws2.append(["月份", "PPM"])
    for point in dashboard_data["ppm_trend"]:
        ws2.append([point["month"], round(point["ppm"], 2)])
    
    # Save to bytes
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    return output.getvalue()
```

- [ ] **Step 2: Commit service layer**

```bash
git add backend/app/services/supplier_quality_service.py
git commit -m "feat(backend): add supplier quality dashboard service with aggregation logic"
```

---

## Task 4: Add Quality API Routes

**Files:**
- Modify: `backend/app/api/supplier.py`

- [ ] **Step 1: Add quality dashboard routes to supplier.py**

Insert after the existing imports and before the first route:

```python
# Add to imports at top
from datetime import date as date_type
from typing import List as TypingList
from fastapi.responses import StreamingResponse
from io import BytesIO

# Add after existing imports
from app.services import supplier_quality_service
```

Then add these routes after the existing `/stats` route (around line 18):

```python
# ─── Quality Dashboard ───

@router.get("/quality/dashboard", response_model=schemas.supplier.QualityDashboardResponse)
async def get_quality_dashboard(
    start_date: date_type | None = Query(None),
    end_date: date_type | None = Query(None),
    product_line_code: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Get supplier quality dashboard KPIs, trends, and rankings."""
    return await supplier_quality_service.get_quality_dashboard(
        db, start_date, end_date, product_line_code
    )


@router.get("/quality/supplier/{supplier_id}", response_model=schemas.supplier.SupplierQualityDetailResponse)
async def get_supplier_quality_detail(
    supplier_id: uuid.UUID,
    start_date: date_type | None = Query(None),
    end_date: date_type | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Get quality stats and trends for a single supplier."""
    return await supplier_quality_service.get_supplier_quality_detail(
        db, str(supplier_id), start_date, end_date
    )


@router.get("/quality/compare", response_model=schemas.supplier.SupplierCompareResponse)
async def get_supplier_compare(
    supplier_ids: str = Query(..., description="Comma-separated supplier IDs"),
    start_date: date_type | None = Query(None),
    end_date: date_type | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Compare multiple suppliers across quality metrics."""
    ids = supplier_ids.split(",")
    return await supplier_quality_service.get_supplier_compare(
        db, ids, start_date, end_date
    )


@router.get("/quality/export")
async def export_quality_dashboard(
    start_date: date_type | None = Query(None),
    end_date: date_type | None = Query(None),
    product_line_code: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Export supplier quality dashboard to Excel."""
    excel_bytes = await supplier_quality_service.export_quality_dashboard_excel(
        db, start_date, end_date, product_line_code
    )
    
    filename = f"supplier_quality_{date_type.today().strftime('%Y%m%d')}.xlsx"
    
    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 2: Commit API routes**

```bash
git add backend/app/api/supplier.py
git commit -m "feat(backend): add supplier quality dashboard API routes"
```

---

## Task 5: Add Frontend Quality Types

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add quality dashboard types to types/index.ts**

Append to the end of the file:

```typescript
// ─── Supplier Quality Dashboard ───

export interface QualityKPI {
  total_suppliers: number;
  overall_ppm: number;
  batch_acceptance_rate: number;
  open_scar_count: number;
}

export interface PPMTrendPoint {
  month: string;
  ppm: number;
}

export interface GradeDistribution {
  A: number;
  B: number;
  C: number;
  D: number;
}

export interface SupplierRankingItem {
  supplier_id: string;
  supplier_no: string;
  name: string;
  grade: string;
  ppm: number;
  batch_acceptance_rate: number;
  delivery_rate: number;
  open_scar_count: number;
}

export interface QualityDashboardResponse {
  kpi: QualityKPI;
  ppm_trend: PPMTrendPoint[];
  grade_distribution: GradeDistribution;
  ranking: SupplierRankingItem[];
}

export interface SupplierQualityStats {
  grade: string;
  total_score: number;
  quality_score: number;
  delivery_score: number;
  service_score: number;
  ppm: number;
  batch_acceptance_rate: number;
  total_inspections: number;
  accepted_count: number;
  scar_count: number;
  open_scar_count: number;
}

export interface SupplierQualityDetailResponse {
  supplier: Supplier;
  stats: SupplierQualityStats;
  ppm_trend: PPMTrendPoint[];
  acceptance_trend: { month: string; rate: number }[];
}

export interface SupplierCompareItem {
  supplier_id: string;
  name: string;
  supplier_no: string;
  grade: string;
  ppm: number;
  batch_acceptance_rate: number;
  delivery_rate: number;
  open_scar_count: number;
  quality_score: number;
  delivery_score: number;
  service_score: number;
}

export interface SupplierCompareResponse {
  suppliers: SupplierCompareItem[];
  ppm_trends: Record<string, PPMTrendPoint[]>;
}
```

- [ ] **Step 2: Commit type definitions**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(frontend): add supplier quality dashboard TypeScript types"
```

---

## Task 6: Add Frontend API Client Functions

**Files:**
- Modify: `frontend/src/api/supplier.ts`

- [ ] **Step 1: Add quality API client functions to supplier.ts**

Append to the end of the file:

```typescript
// ─── Quality Dashboard ───

export async function getQualityDashboard(params?: {
  start_date?: string;
  end_date?: string;
  product_line_code?: string;
}): Promise<QualityDashboardResponse> {
  const resp = await client.get("/suppliers/quality/dashboard", { params });
  return resp.data;
}

export async function getSupplierQualityDetail(
  supplierId: string,
  params?: {
    start_date?: string;
    end_date?: string;
  }
): Promise<SupplierQualityDetailResponse> {
  const resp = await client.get(`/suppliers/quality/supplier/${supplierId}`, { params });
  return resp.data;
}

export async function getSupplierCompare(
  supplierIds: string[],
  params?: {
    start_date?: string;
    end_date?: string;
  }
): Promise<SupplierCompareResponse> {
  const resp = await client.get("/suppliers/quality/compare", {
    params: {
      supplier_ids: supplierIds.join(","),
      ...params,
    },
  });
  return resp.data;
}

export async function exportQualityDashboard(params?: {
  start_date?: string;
  end_date?: string;
  product_line_code?: string;
}): Promise<void> {
  const resp = await client.get("/suppliers/quality/export", {
    params,
    responseType: "blob",
  });
  
  const url = window.URL.createObjectURL(new Blob([resp.data]));
  const link = document.createElement("a");
  link.href = url;
  link.setAttribute("download", `supplier_quality_${new Date().toISOString().split("T")[0]}.xlsx`);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
```

Also add the imports at the top:

```typescript
import type {
  // ... existing imports ...
  QualityDashboardResponse,
  SupplierQualityDetailResponse,
  SupplierCompareResponse,
} from "../types";
```

- [ ] **Step 2: Commit API client**

```bash
git add frontend/src/api/supplier.ts
git commit -m "feat(frontend): add supplier quality dashboard API client functions"
```

---

## Task 7: Create DashboardView Component

**Files:**
- Create: `frontend/src/pages/supplier/components/DashboardView.tsx`

- [ ] **Step 1: Create DashboardView.tsx**

```tsx
import { useEffect, useState } from "react";
import { Row, Col, Card, Table, Tag, DatePicker, Button, Space, Spin } from "antd";
import { DownloadOutlined } from "@ant-design/icons";
import { Line, Pie } from "@ant-design/charts";
import { getQualityDashboard, exportQualityDashboard } from "../../../api/supplier";
import { useProductLineStore } from "../../../store/productLineStore";
import type { QualityDashboardResponse, SupplierRankingItem } from "../../../types";

const { RangePicker } = DatePicker;

export default function DashboardView() {
  const [data, setData] = useState<QualityDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [dateRange, setDateRange] = useState<[string, string] | null>(null);
  const productLine = useProductLineStore((s) => s.selected);

  useEffect(() => {
    loadDashboard();
  }, [productLine, dateRange]);

  const loadDashboard = async () => {
    setLoading(true);
    try {
      const params: any = {};
      if (dateRange) {
        params.start_date = dateRange[0];
        params.end_date = dateRange[1];
      }
      if (productLine) {
        params.product_line_code = productLine;
      }
      const result = await getQualityDashboard(params);
      setData(result);
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async () => {
    const params: any = {};
    if (dateRange) {
      params.start_date = dateRange[0];
      params.end_date = dateRange[1];
    }
    if (productLine) {
      params.product_line_code = productLine;
    }
    await exportQualityDashboard(params);
  };

  if (loading || !data) {
    return (
      <div style={{ textAlign: "center", padding: "100px 0" }}>
        <Spin size="large" />
      </div>
    );
  }

  const ppmTrendConfig = {
    data: data.ppm_trend,
    xField: "month",
    yField: "ppm",
    point: { size: 4 },
    smooth: true,
  };

  const gradeDistConfig = {
    data: [
      { type: "A", value: data.grade_distribution.A },
      { type: "B", value: data.grade_distribution.B },
      { type: "C", value: data.grade_distribution.C },
      { type: "D", value: data.grade_distribution.D },
    ],
    angleField: "value",
    colorField: "type",
    color: ["#52c41a", "#1677ff", "#faad14", "#ff4d4f"],
    label: { type: "inner", offset: "-30%" },
  };

  const rankingColumns = [
    { title: "排名", width: 60, render: (_: any, __: any, idx: number) => idx + 1 },
    { title: "供应商编号", dataIndex: "supplier_no", key: "supplier_no" },
    { title: "供应商名称", dataIndex: "name", key: "name" },
    {
      title: "评级",
      dataIndex: "grade",
      key: "grade",
      render: (grade: string) => {
        const colors: Record<string, string> = { A: "#52c41a", B: "#1677ff", C: "#faad14", D: "#ff4d4f" };
        return <Tag color={colors[grade]}>{grade}</Tag>;
      },
    },
    {
      title: "PPM",
      dataIndex: "ppm",
      key: "ppm",
      render: (ppm: number) => ppm.toLocaleString(undefined, { maximumFractionDigits: 0 }),
    },
    {
      title: "批次合格率",
      dataIndex: "batch_acceptance_rate",
      key: "batch_acceptance_rate",
      render: (rate: number) => `${(rate * 100).toFixed(1)}%`,
    },
    {
      title: "交付准时率",
      dataIndex: "delivery_rate",
      key: "delivery_rate",
      render: (rate: number) => `${(rate * 100).toFixed(1)}%`,
    },
    {
      title: "开放SCAR",
      dataIndex: "open_scar_count",
      key: "open_scar_count",
      render: (count: number) => (
        <Tag color={count > 0 ? "error" : "success"}>{count}</Tag>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between" }}>
        <RangePicker
          onChange={(dates) => {
            if (dates && dates[0] && dates[1]) {
              setDateRange([dates[0].format("YYYY-MM-DD"), dates[1].format("YYYY-MM-DD")]);
            } else {
              setDateRange(null);
            }
          }}
        />
        <Button icon={<DownloadOutlined />} onClick={handleExport}>
          导出报表
        </Button>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <div style={{ fontSize: 14, color: "#888" }}>供应商总数</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: "#1677ff" }}>
              {data.kpi.total_suppliers}
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <div style={{ fontSize: 14, color: "#888" }}>整体PPM</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: "#52c41a" }}>
              {data.kpi.overall_ppm.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <div style={{ fontSize: 14, color: "#888" }}>批次合格率</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: "#52c41a" }}>
              {(data.kpi.batch_acceptance_rate * 100).toFixed(1)}%
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <div style={{ fontSize: 14, color: "#888" }}>开放SCAR</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: "#faad14" }}>
              {data.kpi.open_scar_count}
            </div>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card title="PPM 趋势">
            <Line {...ppmTrendConfig} />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="评级分布">
            <Pie {...gradeDistConfig} />
          </Card>
        </Col>
      </Row>

      <Card title="供应商排名 (Top 20)" style={{ marginTop: 16 }}>
        <Table
          dataSource={data.ranking}
          columns={rankingColumns}
          rowKey="supplier_id"
          pagination={false}
          size="small"
        />
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Commit DashboardView component**

```bash
git add frontend/src/pages/supplier/components/DashboardView.tsx
git commit -m "feat(frontend): add supplier quality dashboard view with charts and table"
```

---

## Task 8: Create SupplierDetailView Component

**Files:**
- Create: `frontend/src/pages/supplier/components/SupplierDetailView.tsx`

- [ ] **Step 1: Create SupplierDetailView.tsx**

```tsx
import { useEffect, useState } from "react";
import { Card, Tabs, Table, Tag, Spin, Row, Col } from "antd";
import { Line } from "@ant-design/charts";
import { useNavigate, useParams } from "react-router-dom";
import { getSupplierQualityDetail, listCertifications, listEvaluations } from "../../../api/supplier";
import type { SupplierQualityDetailResponse, SupplierCertification, SupplierEvaluation } from "../../../types";

export default function SupplierDetailView() {
  const { supplierId } = useParams<{ supplierId: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<SupplierQualityDetailResponse | null>(null);
  const [certifications, setCertifications] = useState<SupplierCertification[]>([]);
  const [evaluations, setEvaluations] = useState<SupplierEvaluation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (supplierId) {
      loadDetail();
    }
  }, [supplierId]);

  const loadDetail = async () => {
    setLoading(true);
    try {
      const detail = await getSupplierQualityDetail(supplierId!);
      setData(detail);
      
      const [certs, evals] = await Promise.all([
        listCertifications(supplierId!),
        listEvaluations(supplierId!),
      ]);
      setCertifications(certs);
      setEvaluations(evals);
    } finally {
      setLoading(false);
    }
  };

  if (loading || !data) {
    return (
      <div style={{ textAlign: "center", padding: "100px 0" }}>
        <Spin size="large" />
      </div>
    );
  }

  const gradeColors: Record<string, string> = { A: "#52c41a", B: "#1677ff", C: "#faad14", D: "#ff4d4f" };

  const ppmTrendConfig = {
    data: data.ppm_trend,
    xField: "month",
    yField: "ppm",
    point: { size: 4 },
    smooth: true,
  };

  const acceptanceTrendConfig = {
    data: data.acceptance_trend.map((d) => ({ ...d, rate: d.rate * 100 })),
    xField: "month",
    yField: "rate",
    point: { size: 4 },
    smooth: true,
  };

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <Row gutter={16} align="middle">
          <Col flex="auto">
            <h2 style={{ margin: 0 }}>
              {data.supplier.name}
              <Tag color={gradeColors[data.stats.grade]} style={{ marginLeft: 8 }}>
                {data.stats.grade}级
              </Tag>
            </h2>
            <div style={{ color: "#888" }}>{data.supplier.supplier_no}</div>
          </Col>
          <Col>
            <Row gutter={24}>
              <Col style={{ textAlign: "center" }}>
                <div style={{ fontSize: 12, color: "#888" }}>综合得分</div>
                <div style={{ fontSize: 24, fontWeight: 700, color: "#1677ff" }}>
                  {data.stats.total_score.toFixed(0)}
                </div>
              </Col>
              <Col style={{ textAlign: "center" }}>
                <div style={{ fontSize: 12, color: "#888" }}>质量得分</div>
                <div style={{ fontSize: 24, fontWeight: 700 }}>
                  {data.stats.quality_score.toFixed(0)}
                </div>
              </Col>
              <Col style={{ textAlign: "center" }}>
                <div style={{ fontSize: 12, color: "#888" }}>交付得分</div>
                <div style={{ fontSize: 24, fontWeight: 700 }}>
                  {data.stats.delivery_score.toFixed(0)}
                </div>
              </Col>
            </Row>
          </Col>
        </Row>
      </Card>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={12}>
          <Card title="PPM 月度趋势">
            <Line {...ppmTrendConfig} />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="批次合格率趋势">
            <Line {...acceptanceTrendConfig} />
          </Card>
        </Col>
      </Row>

      <Card>
        <Tabs
          items={[
            {
              key: "stats",
              label: "质量统计",
              children: (
                <Row gutter={[16, 16]}>
                  <Col span={6}>
                    <div style={{ fontSize: 12, color: "#888" }}>PPM</div>
                    <div style={{ fontSize: 20, fontWeight: 600 }}>
                      {data.stats.ppm.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </div>
                  </Col>
                  <Col span={6}>
                    <div style={{ fontSize: 12, color: "#888" }}>批次合格率</div>
                    <div style={{ fontSize: 20, fontWeight: 600 }}>
                      {(data.stats.batch_acceptance_rate * 100).toFixed(1)}%
                    </div>
                  </Col>
                  <Col span={6}>
                    <div style={{ fontSize: 12, color: "#888" }}>检验批次</div>
                    <div style={{ fontSize: 20, fontWeight: 600 }}>
                      {data.stats.total_inspections}
                    </div>
                  </Col>
                  <Col span={6}>
                    <div style={{ fontSize: 12, color: "#888" }}>合格批次</div>
                    <div style={{ fontSize: 20, fontWeight: 600 }}>
                      {data.stats.accepted_count}
                    </div>
                  </Col>
                  <Col span={6}>
                    <div style={{ fontSize: 12, color: "#888" }}>SCAR总数</div>
                    <div style={{ fontSize: 20, fontWeight: 600 }}>
                      {data.stats.scar_count}
                    </div>
                  </Col>
                  <Col span={6}>
                    <div style={{ fontSize: 12, color: "#888" }}>开放SCAR</div>
                    <div style={{ fontSize: 20, fontWeight: 600, color: data.stats.open_scar_count > 0 ? "#ff4d4f" : undefined }}>
                      {data.stats.open_scar_count}
                    </div>
                  </Col>
                </Row>
              ),
            },
            {
              key: "certifications",
              label: "资质证书",
              children: (
                <Table
                  dataSource={certifications}
                  columns={[
                    { title: "证书类型", dataIndex: "cert_type" },
                    { title: "证书编号", dataIndex: "cert_no" },
                    { title: "颁发机构", dataIndex: "issued_by" },
                    { title: "有效期", dataIndex: "expiry_date" },
                  ]}
                  rowKey="cert_id"
                  pagination={false}
                  size="small"
                />
              ),
            },
            {
              key: "evaluations",
              label: "评价历史",
              children: (
                <Table
                  dataSource={evaluations}
                  columns={[
                    { title: "评价周期", dataIndex: "eval_period" },
                    { title: "类型", dataIndex: "eval_type" },
                    { title: "评级", dataIndex: "grade", render: (g: string) => <Tag color={gradeColors[g]}>{g}</Tag> },
                    { title: "总分", dataIndex: "total_score" },
                    { title: "质量", dataIndex: "quality_score" },
                    { title: "交付", dataIndex: "delivery_score" },
                  ]}
                  rowKey="eval_id"
                  pagination={false}
                  size="small"
                />
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Commit SupplierDetailView component**

```bash
git add frontend/src/pages/supplier/components/SupplierDetailView.tsx
git commit -m "feat(frontend): add supplier quality detail view with trends and tabs"
```

---

## Task 9: Create CompareView Component

**Files:**
- Create: `frontend/src/pages/supplier/components/CompareView.tsx`

- [ ] **Step 1: Create CompareView.tsx**

```tsx
import { useState } from "react";
import { Card, Select, Table, Tag, Row, Col, Empty } from "antd";
import { Radar, Line } from "@ant-design/charts";
import { getSupplierCompare, listSuppliers } from "../../../api/supplier";
import type { SupplierCompareResponse, Supplier } from "../../../types";

export default function CompareView() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [compareData, setCompareData] = useState<SupplierCompareResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const loadSuppliers = async (search: string) => {
    const result = await listSuppliers({ search, page_size: 20 });
    setSuppliers(result.items);
  };

  const handleCompare = async () => {
    if (selectedIds.length < 2) return;
    
    setLoading(true);
    try {
      const result = await getSupplierCompare(selectedIds);
      setCompareData(result);
    } finally {
      setLoading(false);
    }
  };

  const gradeColors: Record<string, string> = { A: "#52c41a", B: "#1677ff", C: "#faad14", D: "#ff4d4f" };

  const radarConfig = compareData
    ? {
        data: compareData.suppliers.flatMap((s) => [
          { item: "质量", user: s.name, value: s.quality_score },
          { item: "交付", user: s.name, value: s.delivery_score },
          { item: "服务", user: s.name, value: s.service_score },
          { item: "PPM", user: s.name, value: 100 - Math.min(s.ppm / 200, 100) },
          { item: "SCAR", user: s.name, value: 100 - s.open_scar_count * 10 },
        ]),
        xField: "item",
        yField: "value",
        seriesField: "user",
        meta: { value: { alias: "分数", min: 0, max: 100 } },
      }
    : null;

  const compareColumns = [
    { title: "指标", dataIndex: "metric" },
    ...selectedIds.map((id) => {
      const s = compareData?.suppliers.find((x) => x.supplier_id === id);
      return {
        title: s?.name || id,
        render: (_: any, record: any) => record[id],
      };
    }),
  ];

  const compareTableData = compareData
    ? [
        {
          key: "grade",
          metric: "评级",
          ...Object.fromEntries(
            compareData.suppliers.map((s) => [
              s.supplier_id,
              <Tag color={gradeColors[s.grade]}>{s.grade}</Tag>,
            ])
          ),
        },
        {
          key: "ppm",
          metric: "PPM",
          ...Object.fromEntries(
            compareData.suppliers.map((s) => [s.supplier_id, s.ppm.toFixed(0)])
          ),
        },
        {
          key: "acceptance",
          metric: "批次合格率",
          ...Object.fromEntries(
            compareData.suppliers.map((s) => [
              s.supplier_id,
              `${(s.batch_acceptance_rate * 100).toFixed(1)}%`,
            ])
          ),
        },
        {
          key: "delivery",
          metric: "交付准时率",
          ...Object.fromEntries(
            compareData.suppliers.map((s) => [
              s.supplier_id,
              `${(s.delivery_rate * 100).toFixed(1)}%`,
            ])
          ),
        },
        {
          key: "scar",
          metric: "开放SCAR",
          ...Object.fromEntries(
            compareData.suppliers.map((s) => [
              s.supplier_id,
              <Tag color={s.open_scar_count > 0 ? "error" : "success"}>
                {s.open_scar_count}
              </Tag>,
            ])
          ),
        },
      ]
    : [];

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <Row gutter={16} align="middle">
          <Col flex="auto">
            <Select
              mode="multiple"
              style={{ width: "100%" }}
              placeholder="选择2-4家供应商进行对比"
              maxTagCount={4}
              filterOption={false}
              onSearch={loadSuppliers}
              onChange={(values) => {
                setSelectedIds(values);
                if (values.length >= 2) {
                  setTimeout(handleCompare, 100);
                } else {
                  setCompareData(null);
                }
              }}
              options={suppliers.map((s) => ({
                label: `${s.supplier_no} - ${s.name}`,
                value: s.supplier_id,
              }))}
            />
          </Col>
        </Row>
      </Card>

      {compareData ? (
        <Row gutter={16}>
          <Col span={12}>
            <Card title="雷达图对比">
              <Radar {...radarConfig!} />
            </Card>
          </Col>
          <Col span={12}>
            <Card title="指标明细对比">
              <Table
                dataSource={compareTableData}
                columns={compareColumns}
                pagination={false}
                size="small"
              />
            </Card>
          </Col>
        </Row>
      ) : (
        <Empty description="请选择至少2家供应商" />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit CompareView component**

```bash
git add frontend/src/pages/supplier/components/CompareView.tsx
git commit -m "feat(frontend): add supplier comparison view with radar chart"
```

---

## Task 10: Create Main SupplierQualityPage

**Files:**
- Create: `frontend/src/pages/supplier/SupplierQualityPage.tsx`

- [ ] **Step 1: Create SupplierQualityPage.tsx**

```tsx
import { useState } from "react";
import { Tabs } from "antd";
import { BarChartOutlined, UserOutlined, CompareOutlined } from "@ant-design/icons";
import DashboardView from "./components/DashboardView";
import SupplierDetailView from "./components/SupplierDetailView";
import CompareView from "./components/CompareView";

export default function SupplierQualityPage() {
  const [activeTab, setActiveTab] = useState("dashboard");

  return (
    <div>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: "dashboard",
            label: (
              <span>
                <BarChartOutlined />
                汇总看板
              </span>
            ),
            children: <DashboardView />,
          },
          {
            key: "detail",
            label: (
              <span>
                <UserOutlined />
                供应商详情
              </span>
            ),
            children: <SupplierDetailView />,
          },
          {
            key: "compare",
            label: (
              <span>
                <CompareOutlined />
                对比分析
              </span>
            ),
            children: <CompareView />,
          },
        ]}
      />
    </div>
  );
}
```

- [ ] **Step 2: Commit main page**

```bash
git add frontend/src/pages/supplier/SupplierQualityPage.tsx
git commit -m "feat(frontend): add supplier quality main page with tab navigation"
```

---

## Task 11: Add Route and Navigation

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`

- [ ] **Step 1: Add route to App.tsx**

Add import:

```tsx
import SupplierQualityPage from "./pages/supplier/SupplierQualityPage";
```

Add route after existing supplier routes:

```tsx
<Route path="/suppliers/quality" element={<SupplierQualityPage />} />
<Route path="/suppliers/quality/:supplierId" element={<SupplierQualityPage />} />
```

- [ ] **Step 2: Add sidebar menu entry to AppLayout.tsx**

In the `menuItems` array, add after the suppliers entry:

```tsx
{
  key: "/suppliers/quality",
  icon: <BarChartOutlined />,
  label: "供货质量看板",
},
```

Also add `BarChartOutlined` to the imports at the top.

- [ ] **Step 3: Commit route and navigation**

```bash
git add frontend/src/App.tsx frontend/src/components/layout/AppLayout.tsx
git commit -m "feat(frontend): add supplier quality dashboard route and navigation"
```

---

## Task 12: Test and Verify

- [ ] **Step 1: Start backend server**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Expected: Backend starts without errors

- [ ] **Step 2: Start frontend server**

```bash
cd /Users/sam/Documents/Code/OpenQMS/frontend
npm run dev
```

Expected: Frontend starts and compiles without errors

- [ ] **Step 3: Test quality dashboard in browser**

1. Navigate to `http://localhost:5173/suppliers/quality`
2. Verify the three tabs appear: 汇总看板, 供应商详情, 对比分析
3. Check that KPI cards load with data
4. Verify charts render correctly
5. Test date range filter
6. Test export button

Expected: All views render without errors, charts display correctly

- [ ] **Step 4: Commit final verification**

```bash
git add -A
git commit -m "test: verify supplier quality dashboard functionality"
```

---

## Completion Checklist

- [ ] All dependencies installed (openpyxl, @ant-design/charts)
- [ ] Backend quality service implements aggregation logic
- [ ] API routes return correct data
- [ ] Frontend types match backend schemas
- [ ] Dashboard view displays KPIs and charts
- [ ] Detail view shows supplier-specific trends
- [ ] Compare view enables multi-supplier comparison
- [ ] Excel export generates valid file
- [ ] Navigation and routing work correctly
- [ ] No TypeScript or lint errors
