"""Group dashboard, comparison, shared suppliers, and cross-factory audit service."""
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.factory import Factory
from app.models.fmea import FMEADocument
from app.models.capa import CAPAEightD
from app.models.spc import SPCAlarm
from app.models.iqc_inspection import IqcInspection
from app.models.supplier import SupplierSCAR
from app.models.supplier_risk import SupplierRiskAlert
from app.models.audit_finding import AuditFinding
from app.models.audit_program import AuditProgram, AuditProgramTargetFactory
from app.models.audit_plan import AuditPlan
from app.models.supplier import Supplier
from app.models.supplier_shared_profile import SupplierSharedProfile
from app.schemas.group import (
    FactoryKPI,
    GroupDashboardResponse,
    FactoryComparisonItem,
    FactoryComparisonResponse,
    SharedSupplierResponse,
    CrossFactoryAuditResponse,
)


async def get_group_dashboard(db: AsyncSession) -> GroupDashboardResponse:
    """Aggregate KPIs across all active factories."""
    result = await db.execute(
        select(Factory).where(Factory.is_active == True).order_by(Factory.code)
    )
    factories = list(result.scalars().all())

    if not factories:
        return GroupDashboardResponse(factories=[], totals=FactoryKPI(
            factory_id=uuid.UUID(int=0), factory_code="", factory_name="合计",
        ))

    factory_ids = [f.id for f in factories]

    # Open FMEA count per factory (draft or in_review)
    fmea_counts = dict.fromkeys(factory_ids, 0)
    rows = await db.execute(
        select(FMEADocument.factory_id, func.count(FMEADocument.fmea_id))
        .where(FMEADocument.factory_id.in_(factory_ids))
        .where(FMEADocument.status.in_(["draft", "in_review"]))
        .group_by(FMEADocument.factory_id)
    )
    for fid, cnt in rows.all():
        fmea_counts[fid] = cnt

    # Open CAPA count per factory
    capa_counts = dict.fromkeys(factory_ids, 0)
    rows = await db.execute(
        select(CAPAEightD.factory_id, func.count(CAPAEightD.report_id))
        .where(CAPAEightD.factory_id.in_(factory_ids))
        .where(CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"]))
        .group_by(CAPAEightD.factory_id)
    )
    for fid, cnt in rows.all():
        capa_counts[fid] = cnt

    # Overdue CAPA count per factory
    overdue_capa_counts = dict.fromkeys(factory_ids, 0)
    today = date.today()
    rows = await db.execute(
        select(CAPAEightD.factory_id, func.count(CAPAEightD.report_id))
        .where(CAPAEightD.factory_id.in_(factory_ids))
        .where(CAPAEightD.status.notin_(["D8_CLOSURE", "ARCHIVED"]))
        .where(CAPAEightD.due_date < today)
        .group_by(CAPAEightD.factory_id)
    )
    for fid, cnt in rows.all():
        overdue_capa_counts[fid] = cnt

    # Active SPC alarms per factory
    spc_counts = dict.fromkeys(factory_ids, 0)
    rows = await db.execute(
        select(SPCAlarm.factory_id, func.count(SPCAlarm.alarm_id))
        .where(SPCAlarm.factory_id.in_(factory_ids))
        .where(SPCAlarm.status == "open")
        .group_by(SPCAlarm.factory_id)
    )
    for fid, cnt in rows.all():
        spc_counts[fid] = cnt

    # Pending IQC inspections per factory
    iqc_counts = dict.fromkeys(factory_ids, 0)
    rows = await db.execute(
        select(IqcInspection.factory_id, func.count(IqcInspection.inspection_id))
        .where(IqcInspection.factory_id.in_(factory_ids))
        .where(IqcInspection.status == "pending")
        .group_by(IqcInspection.factory_id)
    )
    for fid, cnt in rows.all():
        iqc_counts[fid] = cnt

    # Open SCARs per factory
    scar_counts = dict.fromkeys(factory_ids, 0)
    rows = await db.execute(
        select(SupplierSCAR.factory_id, func.count(SupplierSCAR.scar_id))
        .where(SupplierSCAR.factory_id.in_(factory_ids))
        .where(SupplierSCAR.status.notin_(["closed", "cancelled"]))
        .group_by(SupplierSCAR.factory_id)
    )
    for fid, cnt in rows.all():
        scar_counts[fid] = cnt

    # Open supplier risk alerts per factory
    risk_counts = dict.fromkeys(factory_ids, 0)
    rows = await db.execute(
        select(SupplierRiskAlert.factory_id, func.count(SupplierRiskAlert.alert_id))
        .where(SupplierRiskAlert.factory_id.in_(factory_ids))
        .where(SupplierRiskAlert.status == "open")
        .group_by(SupplierRiskAlert.factory_id)
    )
    for fid, cnt in rows.all():
        risk_counts[fid] = cnt

    # Recent audit findings per factory (last 90 days)
    finding_counts = dict.fromkeys(factory_ids, 0)
    ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)
    rows = await db.execute(
        select(AuditFinding.factory_id, func.count(AuditFinding.finding_id))
        .where(AuditFinding.factory_id.in_(factory_ids))
        .where(AuditFinding.created_at >= ninety_days_ago)
        .group_by(AuditFinding.factory_id)
    )
    for fid, cnt in rows.all():
        finding_counts[fid] = cnt

    # Build per-factory KPIs
    factory_kpis = []
    for f in factories:
        factory_kpis.append(FactoryKPI(
            factory_id=f.id,
            factory_code=f.code,
            factory_name=f.name,
            open_fmea_count=fmea_counts.get(f.id, 0),
            open_capa_count=capa_counts.get(f.id, 0),
            overdue_capa_count=overdue_capa_counts.get(f.id, 0),
            active_spc_alarms=spc_counts.get(f.id, 0),
            pending_iqc_inspections=iqc_counts.get(f.id, 0),
            open_scars=scar_counts.get(f.id, 0),
            open_supplier_risk_alerts=risk_counts.get(f.id, 0),
            recent_audit_findings=finding_counts.get(f.id, 0),
        ))

    # Aggregate totals
    totals = FactoryKPI(
        factory_id=uuid.UUID(int=0),
        factory_code="",
        factory_name="合计",
        open_fmea_count=sum(k.open_fmea_count for k in factory_kpis),
        open_capa_count=sum(k.open_capa_count for k in factory_kpis),
        overdue_capa_count=sum(k.overdue_capa_count for k in factory_kpis),
        active_spc_alarms=sum(k.active_spc_alarms for k in factory_kpis),
        pending_iqc_inspections=sum(k.pending_iqc_inspections for k in factory_kpis),
        open_scars=sum(k.open_scars for k in factory_kpis),
        open_supplier_risk_alerts=sum(k.open_supplier_risk_alerts for k in factory_kpis),
        recent_audit_findings=sum(k.recent_audit_findings for k in factory_kpis),
    )

    return GroupDashboardResponse(factories=factory_kpis, totals=totals)


async def get_factory_comparison(
    db: AsyncSession,
    metric_names: list[str] | None = None,
) -> FactoryComparisonResponse:
    """Compare factories side by side on standardized metrics."""
    default_metrics = [
        "open_fmea_count", "open_capa_count", "overdue_capa_count",
        "active_spc_alarms", "pending_iqc_inspections", "open_scars",
        "open_supplier_risk_alerts", "recent_audit_findings",
    ]
    metrics = metric_names if metric_names else default_metrics

    # Reuse dashboard data
    dashboard = await get_group_dashboard(db)

    items = []
    for kpi in dashboard.factories:
        metric_values = {}
        for m in metrics:
            if hasattr(kpi, m):
                metric_values[m] = getattr(kpi, m)
            else:
                metric_values[m] = None
        items.append(FactoryComparisonItem(
            factory_id=kpi.factory_id,
            factory_code=kpi.factory_code,
            factory_name=kpi.factory_name,
            metrics=metric_values,
        ))

    return FactoryComparisonResponse(factories=items, metric_names=metrics)


async def get_shared_suppliers(db: AsyncSession) -> list[SharedSupplierResponse]:
    """Get suppliers with shared profiles across factories."""
    rows = await db.execute(
        select(
            SupplierSharedProfile.id,
            SupplierSharedProfile.unified_credit_code,
            SupplierSharedProfile.name,
            SupplierSharedProfile.short_name,
            SupplierSharedProfile.industry,
        )
        .join(Supplier, Supplier.shared_profile_id == SupplierSharedProfile.id)
        .group_by(
            SupplierSharedProfile.id,
            SupplierSharedProfile.unified_credit_code,
            SupplierSharedProfile.name,
            SupplierSharedProfile.short_name,
            SupplierSharedProfile.industry,
        )
        .having(func.count(Supplier.supplier_id) > 1)
    )
    profiles = rows.all()

    results = []
    for pid, credit_code, name, short_name, industry in profiles:
        supp_rows = await db.execute(
            select(
                Supplier.factory_id,
                Factory.code,
                Supplier.status,
            )
            .join(Factory, Supplier.factory_id == Factory.id)
            .where(Supplier.shared_profile_id == pid)
        )
        evaluations = []
        for fid, fcode, status in supp_rows.all():
            evaluations.append({
                "factory_id": str(fid),
                "factory_code": fcode,
                "grade": status,
            })

        results.append(SharedSupplierResponse(
            shared_profile_id=pid,
            unified_credit_code=credit_code,
            name=name,
            short_name=short_name,
            industry=industry,
            factory_evaluations=evaluations,
        ))

    return results


async def get_cross_factory_audits(db: AsyncSession) -> list[CrossFactoryAuditResponse]:
    """Get audit programs that span multiple factories."""
    rows = await db.execute(
        select(
            AuditProgram.program_id,
            AuditProgram.program_no,
            AuditProgram.audit_type,
            AuditProgram.status,
        )
        .join(AuditProgramTargetFactory, AuditProgramTargetFactory.program_id == AuditProgram.program_id)
        .group_by(
            AuditProgram.program_id,
            AuditProgram.program_no,
            AuditProgram.audit_type,
            AuditProgram.status,
        )
        .having(func.count(AuditProgramTargetFactory.factory_id) > 1)
    )
    programs = rows.all()

    results = []
    for pid, pno, atype, status in programs:
        tf_rows = await db.execute(
            select(AuditProgramTargetFactory.factory_id)
            .where(AuditProgramTargetFactory.program_id == pid)
        )
        target_ids = [row[0] for row in tf_rows.all()]

        f_rows = await db.execute(
            select(Factory.id, Factory.code)
            .where(Factory.id.in_(target_ids))
        )
        id_to_code = {row[0]: row[1] for row in f_rows.all()}

        # Count findings via AuditPlan join
        finding_count = await db.scalar(
            select(func.count(AuditFinding.finding_id))
            .join(AuditPlan, AuditFinding.audit_id == AuditPlan.audit_id)
            .where(AuditPlan.program_id == pid)
        ) or 0

        results.append(CrossFactoryAuditResponse(
            program_id=pid,
            program_no=pno,
            audit_type=atype,
            status=status,
            target_factory_ids=target_ids,
            target_factory_codes=[id_to_code.get(fid, "") for fid in target_ids],
            finding_count=finding_count,
        ))

    return results