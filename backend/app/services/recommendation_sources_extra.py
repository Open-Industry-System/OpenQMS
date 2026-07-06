from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models.iqc_inspection import IqcInspection
from app.models.spc import InspectionCharacteristic, SPCAlarm
from app.services.recommendation_types import RecommendationCandidate, RecommendationContext
from app.services import spc_service


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
