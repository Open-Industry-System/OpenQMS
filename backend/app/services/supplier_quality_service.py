import uuid
from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.iqc_inspection import IqcInspection
from app.models.supplier import Supplier, SupplierEvaluation, SupplierSCAR


async def get_quality_dashboard(
    db: AsyncSession,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    product_line_code: Optional[str] = None,
    factory_id: uuid.UUID | None = None,
) -> dict:
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=180)

    iqc_filter = [
        IqcInspection.inspection_date >= start_date,
        IqcInspection.inspection_date <= end_date,
    ]
    if product_line_code:
        iqc_filter.append(IqcInspection.product_line_code == product_line_code)
    if factory_id is not None and hasattr(IqcInspection, "factory_id"):
        iqc_filter.append(IqcInspection.factory_id == factory_id)

    # Overall PPM
    ppm_result = await db.execute(
        select(
            func.coalesce(func.sum(IqcInspection.defect_qty), 0).label("total_defects"),
            func.coalesce(func.sum(IqcInspection.lot_qty), 0).label("total_lot_qty"),
        ).where(*iqc_filter)
    )
    ppm_row = ppm_result.one()
    overall_ppm = (
        (ppm_row.total_defects / ppm_row.total_lot_qty * 1_000_000)
        if ppm_row.total_lot_qty > 0 else 0.0
    )

    # Batch acceptance rate
    acceptance_result = await db.execute(
        select(
            func.count().label("total"),
            func.count(case((IqcInspection.inspection_result == "accepted", 1))).label("accepted"),
        ).where(*iqc_filter)
    )
    acc_row = acceptance_result.one()
    batch_acceptance_rate = acc_row.accepted / acc_row.total if acc_row.total > 0 else 0.0

    # Open SCAR count
    open_scar_count = await db.scalar(
        select(func.count()).select_from(SupplierSCAR).where(SupplierSCAR.status != "closed")
    ) or 0

    # Total suppliers
    total_suppliers = await db.scalar(select(func.count()).select_from(Supplier)) or 0

    # PPM trend by month
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
    ppm_trend = [
        {
            "month": f"{int(row.year)}-{int(row.month):02d}",
            "ppm": (row.defects / row.lots * 1_000_000) if row.lots > 0 else 0.0,
        }
        for row in trend_result.all()
    ]

    # Grade distribution from latest evaluations using MAX(created_at)
    latest_eval_subq = (
        select(
            SupplierEvaluation.supplier_id,
            func.max(SupplierEvaluation.created_at).label("max_created_at"),
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
                SupplierEvaluation.created_at == latest_eval_subq.c.max_created_at,
            ),
        )
        .group_by(SupplierEvaluation.grade)
    )
    grade_distribution = {"A": 0, "B": 0, "C": 0, "D": 0}
    for row in grade_result.all():
        if row.grade in grade_distribution:
            grade_distribution[row.grade] = row.count

    # Supplier ranking (top 20)
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
                SupplierEvaluation.created_at == latest_eval_subq.c.max_created_at,
            ),
        )
        .order_by(SupplierEvaluation.total_score.desc())
        .limit(20)
    )
    ranking_rows = ranking_result.all()

    ranking = []
    for row in ranking_rows:
        supp_ppm_result = await db.execute(
            select(
                func.coalesce(func.sum(IqcInspection.defect_qty), 0),
                func.coalesce(func.sum(IqcInspection.lot_qty), 0),
            ).where(IqcInspection.supplier_id == row.supplier_id, *iqc_filter[2:])
        )
        supp_ppm_row = supp_ppm_result.one()
        supp_ppm = (
            (supp_ppm_row[0] / supp_ppm_row[1] * 1_000_000)
            if supp_ppm_row[1] > 0 else 0.0
        )

        supp_acc_result = await db.execute(
            select(
                func.count(),
                func.count(case((IqcInspection.inspection_result == "accepted", 1))),
            ).where(IqcInspection.supplier_id == row.supplier_id, *iqc_filter[2:])
        )
        supp_acc_row = supp_acc_result.one()
        supp_acc_rate = supp_acc_row[1] / supp_acc_row[0] if supp_acc_row[0] > 0 else 0.0

        supp_scar_count = await db.scalar(
            select(func.count()).select_from(SupplierSCAR)
            .where(SupplierSCAR.supplier_id == row.supplier_id, SupplierSCAR.status != "closed")
        ) or 0

        delivery_rate = 0.0
        eval_result = await db.execute(
            select(SupplierEvaluation.delivery_score)
            .where(SupplierEvaluation.supplier_id == row.supplier_id)
            .order_by(SupplierEvaluation.created_at.desc()).limit(1)
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
    factory_id: uuid.UUID | None = None,
) -> dict:
    from app.services.supplier_service import get_supplier

    supplier = await get_supplier(db, supplier_id)

    if not start_date:
        start_date = date.today() - timedelta(days=180)
    if not end_date:
        end_date = date.today()

    # Latest evaluation via MAX(created_at)
    latest_eval_subq = (
        select(
            SupplierEvaluation.supplier_id,
            func.max(SupplierEvaluation.created_at).label("max_created_at"),
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
                SupplierEvaluation.created_at == latest_eval_subq.c.max_created_at,
            ),
        )
        .limit(1)
    )
    eval_row = latest_eval.scalar_one_or_none()

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

    scar_count = await db.scalar(
        select(func.count()).select_from(SupplierSCAR)
        .where(SupplierSCAR.supplier_id == supplier_id)
    ) or 0

    open_scar_count = await db.scalar(
        select(func.count()).select_from(SupplierSCAR)
        .where(SupplierSCAR.supplier_id == supplier_id, SupplierSCAR.status != "closed")
    ) or 0

    trend_result = await db.execute(
        select(
            func.extract("year", IqcInspection.inspection_date),
            func.extract("month", IqcInspection.inspection_date),
            func.coalesce(func.sum(IqcInspection.defect_qty), 0),
            func.coalesce(func.sum(IqcInspection.lot_qty), 0),
        ).where(*iqc_filter).group_by("year", "month").order_by("year", "month")
    )
    ppm_trend = [
        {
            "month": f"{int(row[0])}-{int(row[1]):02d}",
            "ppm": (row[2] / row[3] * 1_000_000) if row[3] > 0 else 0.0,
        }
        for row in trend_result.all()
    ]

    acc_trend_result = await db.execute(
        select(
            func.extract("year", IqcInspection.inspection_date),
            func.extract("month", IqcInspection.inspection_date),
            func.count(),
            func.count(case((IqcInspection.inspection_result == "accepted", 1))),
        ).where(*iqc_filter).group_by("year", "month").order_by("year", "month")
    )
    acceptance_trend = [
        {
            "month": f"{int(row[0])}-{int(row[1]):02d}",
            "rate": row[3] / row[2] if row[2] > 0 else 0.0,
        }
        for row in acc_trend_result.all()
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
    factory_id: uuid.UUID | None = None,
) -> dict:
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

    return {"suppliers": suppliers, "ppm_trends": ppm_trends}


async def export_quality_dashboard_excel(
    db: AsyncSession,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    product_line_code: Optional[str] = None,
    factory_id: uuid.UUID | None = None,
) -> bytes:
    from app.utils.excel import append_row, create_workbook, workbook_to_bytes

    dashboard_data = await get_quality_dashboard(db, start_date, end_date, product_line_code, factory_id=factory_id)

    headers = ["排名", "供应商编号", "供应商名称", "评级", "PPM", "批次合格率", "交付准时率", "开放SCAR"]
    wb, ws = create_workbook("供应商质量排名", headers)

    for idx, item in enumerate(dashboard_data["ranking"], 1):
        append_row(ws, [
            idx,
            item["supplier_no"],
            item["name"],
            item["grade"],
            round(item["ppm"], 2),
            f"{item['batch_acceptance_rate'] * 100:.2f}%",
            f"{item['delivery_rate'] * 100:.2f}%",
            item["open_scar_count"],
        ])

    ws2 = wb.create_sheet("PPM月度趋势")
    ws2.append(["月份", "PPM"])
    for point in dashboard_data["ppm_trend"]:
        ws2.append([point["month"], round(point["ppm"], 2)])

    return workbook_to_bytes(wb)
