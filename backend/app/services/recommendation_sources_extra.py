from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

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
