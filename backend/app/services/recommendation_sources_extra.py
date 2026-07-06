import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import distinct, func, select

from app.models.iqc_inspection import IqcInspection
from app.models.spc import InspectionCharacteristic, SPCAlarm
from app.models.supplier import SupplierSCAR
from app.services import spc_service, supplier_quality_service
from app.services.recommendation_types import RecommendationCandidate, RecommendationContext

logger = logging.getLogger(__name__)


class SPCAnomalySource:
    name = "spc_anomaly"

    def __init__(self, db, embedding_provider=None):
        self.db = db

    async def should_skip(self, context: RecommendationContext) -> str | None:
        pl = context.capa_data.get("product_line_code")
        fid = context.factory_id  # R1-修复：factory_id 隔离
        since = datetime.now(timezone.utc) - timedelta(days=30)
        cnt = await self.db.scalar(
            select(func.count())
            .select_from(SPCAlarm)
            .join(InspectionCharacteristic, SPCAlarm.ic_id == InspectionCharacteristic.ic_id)
            .where(
                InspectionCharacteristic.product_line == pl,
                InspectionCharacteristic.factory_id == fid,  # R1-修复
                SPCAlarm.factory_id == fid,  # R14-修复：spc_alarms 自身也带 factory_id，按 ADR-0003 显式过滤主表
                SPCAlarm.triggered_at >= since,
            )
        )
        return "产品线暂无 SPC 数据" if cnt == 0 else None

    async def retrieve(self, context: RecommendationContext) -> list[RecommendationCandidate]:
        pl = context.capa_data.get("product_line_code")
        fid = context.factory_id  # R1-修复
        since = datetime.now(timezone.utc) - timedelta(days=30)
        alarms = (
            await self.db.execute(
                select(SPCAlarm)
                .join(InspectionCharacteristic, SPCAlarm.ic_id == InspectionCharacteristic.ic_id)
                .where(
                    InspectionCharacteristic.product_line == pl,
                    InspectionCharacteristic.factory_id == fid,  # R1-修复
                    SPCAlarm.factory_id == fid,  # R14-修复：主表 factory_id 过滤
                    SPCAlarm.triggered_at >= since,
                )
                .order_by(SPCAlarm.triggered_at.desc())
            )
        ).scalars().all()
        cands = []
        for alarm in alarms[:10]:
            try:
                matches = await spc_service.match_fmea_for_alarm(self.db, alarm)
            except Exception:
                matches = []
            for m in (matches or []):
                cands.append(
                    RecommendationCandidate(
                        source="spc_anomaly",
                        content=f"SPC 判异：规则 {alarm.rule_no} 触发，关联失效模式 {m.get('failure_mode_name', '')}",
                        category=None,
                        confidence=0.5,
                        match_reason="SPC 判异关联失效模式",
                        metadata={
                            "spc_chart_id": str(alarm.ic_id),
                            "alarm_id": str(alarm.alarm_id),
                            "failure_mode_node_id": m.get("failure_mode_node_id"),
                            "product_line_code": pl,
                            "factory_id": str(fid),
                        },
                    )
                )
        return cands


class IQCSource:
    name = "iqc"

    def __init__(self, db, embedding_provider=None):
        self.db = db

    async def should_skip(self, context: RecommendationContext) -> str | None:
        pl = context.capa_data.get("product_line_code")
        fid = context.factory_id
        since = datetime.now(timezone.utc) - timedelta(days=30)
        cnt = await self.db.scalar(
            select(func.count())
            .select_from(IqcInspection)
            .where(
                IqcInspection.product_line_code == pl,
                IqcInspection.factory_id == fid,
                IqcInspection.defect_qty > 0,
                IqcInspection.inspection_date >= since.date(),
            )
        )
        return "产品线暂无 IQC 不良数据" if cnt == 0 else None

    async def retrieve(self, context: RecommendationContext) -> list[RecommendationCandidate]:
        pl = context.capa_data.get("product_line_code")
        fid = context.factory_id
        since = datetime.now(timezone.utc) - timedelta(days=30)
        inspections = (
            await self.db.execute(
                select(IqcInspection)
                .where(
                    IqcInspection.product_line_code == pl,
                    IqcInspection.factory_id == fid,
                    IqcInspection.defect_qty > 0,
                    IqcInspection.inspection_date >= since.date(),
                )
                .order_by(IqcInspection.inspection_date.desc(), IqcInspection.created_at.desc())
                .limit(10)
            )
        ).scalars().all()

        cands = []
        for insp in inspections:
            part_name = insp.part_name or insp.part_no or "未知料号"
            defect = insp.defect_description or "未说明"
            cands.append(
                RecommendationCandidate(
                    source="iqc",
                    content=f"来料不良：{part_name} 缺陷 {defect}（{insp.defect_qty} 件）",
                    category=None,
                    confidence=0.5,
                    match_reason="IQC 来料不良记录",
                    metadata={
                        "supplier_id": str(insp.supplier_id),
                        "part_no": insp.part_no,
                        "inspection_id": str(insp.inspection_id),
                        "defect_qty": insp.defect_qty,
                        "product_line_code": pl,
                        "factory_id": str(fid),
                    },
                )
            )
        return cands


class SupplierHistorySource:
    name = "supplier_history"

    def __init__(self, db, embedding_provider=None):
        self.db = db

    async def should_skip(self, context: RecommendationContext) -> str | None:
        pl = context.capa_data.get("product_line_code")
        fid = context.factory_id
        since = datetime.now(timezone.utc) - timedelta(days=30)
        supplier_ids = set()

        # 路径 (a)：该工厂 + 产品线近 30 天有不良的 IQC 检验
        if pl and fid:
            rows = await self.db.execute(
                select(distinct(IqcInspection.supplier_id)).where(
                    IqcInspection.product_line_code == pl,
                    IqcInspection.factory_id == fid,
                    IqcInspection.defect_qty > 0,
                    IqcInspection.inspection_date >= since.date(),
                )
            )
            supplier_ids.update(rows.scalars().all())

        # 路径 (b)：关联到当前 CAPA 的 SupplierSCAR（工厂级作用域）
        # 注：当前 context.capa_data 未携带 report_id，此分支在未来补齐后才生效
        capa_report_id = context.capa_data.get("report_id")
        if capa_report_id and fid:
            scar_rows = await self.db.execute(
                select(distinct(SupplierSCAR.supplier_id)).where(
                    SupplierSCAR.capa_ref_id == capa_report_id,
                    SupplierSCAR.factory_id == fid,
                )
            )
            supplier_ids.update(scar_rows.scalars().all())

        return None if supplier_ids else "产品线无关联供应商历史"

    async def retrieve(self, context: RecommendationContext) -> list[RecommendationCandidate]:
        pl = context.capa_data.get("product_line_code")
        fid = context.factory_id
        since = datetime.now(timezone.utc) - timedelta(days=30)

        # 路径 (a)：近 30 天有不良 IQC 检验的供应商
        rows = await self.db.execute(
            select(distinct(IqcInspection.supplier_id))
            .where(
                IqcInspection.product_line_code == pl,
                IqcInspection.factory_id == fid,
                IqcInspection.defect_qty > 0,
                IqcInspection.inspection_date >= since.date(),
            )
        )
        supplier_ids = list(rows.scalars().all())

        # 路径 (b)：当前 CAPA 关联的 SupplierSCAR 供应商（report_id 已知时生效）
        capa_report_id = context.capa_data.get("report_id")
        if capa_report_id and fid:
            scar_rows = await self.db.execute(
                select(distinct(SupplierSCAR.supplier_id)).where(
                    SupplierSCAR.capa_ref_id == capa_report_id,
                    SupplierSCAR.factory_id == fid,
                )
            )
            supplier_ids.extend(scar_rows.scalars().all())

        # 去重并保留顺序（IQC 优先，SCAR 补充），再限制数量
        supplier_ids = list(dict.fromkeys(supplier_ids))[:5]

        cands = []
        for sid in supplier_ids:
            try:
                detail = await supplier_quality_service.get_supplier_quality_detail(
                    self.db, str(sid), factory_id=fid
                )
            except Exception as exc:
                logger.warning("SupplierHistorySource detail failed for %s: %s", sid, exc)
                continue
            supplier = detail.get("supplier")
            stats = detail.get("stats") or {}
            name = getattr(supplier, "name", None) or "未知"
            grade = stats.get("grade") or "N/A"
            ppm = stats.get("ppm") or 0.0
            scar_count = stats.get("open_scar_count") or 0
            cands.append(
                RecommendationCandidate(
                    source="supplier_history",
                    content=f"供应商 {name} 评级 {grade}，PPM={ppm:.2f}，历史 SCAR {scar_count} 条",
                    category=None,
                    confidence=0.5,
                    match_reason="供应商历史质量表现",
                    metadata={
                        "supplier_id": str(sid),
                        "grade": grade,
                        "ppm": ppm,
                        "scar_count": scar_count,
                        "product_line_code": pl,
                        "factory_id": str(fid),
                    },
                )
            )
        return cands
