import uuid

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.graph.repository import FMEAGraphRepository
from app.models.audit import AuditLog
from app.models.change_impact import ChangeImpactAnalysis
from app.models.fmea import FMEADocument
from app.schemas.change_impact import ChangeImpactAnalysisResponse, ChangeImpactResult


def _calculate_impact_score(result: ChangeImpactResult) -> int:
    """Service 层单点评分算法。

    公式：failure_modes_affected * 2 + ap_upgraded_count * 3 + (max_hop_distance > 2 ? 2 : 0)，封顶 10
    """
    summary = result.summary
    score = (
        summary.failure_modes_affected * 2
        + summary.ap_upgraded_count * 3
        + (2 if summary.max_hop_distance > 2 else 0)
    )
    return min(score, 10)


async def _create_audit_log(
    db: AsyncSession,
    user_id: uuid.UUID,
    action: str,
    target_type: str,
    target_id: uuid.UUID,
    detail: dict | None = None,
) -> AuditLog:
    """Create an AuditLog entry."""
    audit_log = AuditLog(
        table_name=target_type,
        record_id=target_id,
        action=action,
        changed_fields=detail or {},
        operated_by=user_id,
    )
    db.add(audit_log)
    return audit_log


class ChangeImpactService:
    def __init__(self, db: AsyncSession, repo: FMEAGraphRepository | None = None):
        self._db = db
        if repo is not None:
            self._repo = repo
        else:
            # 默认回退到 JSONBRepository（向后兼容）
            from app.graph.jsonb_repository import JSONBRepository
            self._repo = JSONBRepository(db)

    async def analyze(
        self,
        fmea_id: uuid.UUID,
        node_id: str,
        node_type: str,
        node_name: str,
        change_type: str,
        field_name: str | None,
        new_value: str | None,
        old_value: str | None,
        user_id: uuid.UUID,
    ) -> ChangeImpactAnalysisResponse:
        """执行变更影响分析、评分、持久化并记录审计日志。"""
        # 获取 FMEA 以提取 product_line_code
        fmea_result = await self._db.execute(
            select(FMEADocument).where(FMEADocument.fmea_id == fmea_id)
        )
        fmea = fmea_result.scalar_one_or_none()
        if not fmea:
            raise ValueError(f"FMEA document not found: {fmea_id}")

        product_line_code = fmea.product_line_code

        # 调用 Repository 分析（不含评分）
        result = await self._repo.analyze_change_impact(
            fmea_id=fmea_id,
            node_id=node_id,
            change_type=change_type,
            field_name=field_name,
            new_value=new_value,
        )

        # Service 层单点评分
        impact_score = _calculate_impact_score(result)

        # 持久化
        record = ChangeImpactAnalysis(
            fmea_id=fmea_id,
            product_line_code=product_line_code,
            node_id=node_id,
            node_type=node_type,
            node_name=node_name,
            change_type=change_type,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            scope="single_fmea",
            status="completed",
            impact_score=impact_score,
            impact_result=result.model_dump(),
            created_by=user_id,
        )
        self._db.add(record)
        await self._db.flush()
        await self._db.refresh(record)

        # 审计日志
        await _create_audit_log(
            db=self._db,
            user_id=user_id,
            action="ANALYZE",
            target_type="change_impact_analysis",
            target_id=record.id,
            detail={
                "fmea_id": str(fmea_id),
                "node_id": node_id,
                "node_type": node_type,
                "node_name": node_name,
                "change_type": change_type,
                "field_name": field_name,
                "impact_score": impact_score,
            },
        )
        await self._db.commit()
        await self._db.refresh(record)

        return ChangeImpactAnalysisResponse.model_validate(record)

    async def list_by_fmea(
        self, fmea_id: uuid.UUID, page: int = 1, page_size: int = 20
    ) -> tuple[list[ChangeImpactAnalysisResponse], int]:
        """按 FMEA 查询历史分析记录。"""
        count_result = await self._db.execute(
            select(func.count())
            .select_from(ChangeImpactAnalysis)
            .where(ChangeImpactAnalysis.fmea_id == fmea_id)
        )
        total = count_result.scalar() or 0

        query = (
            select(ChangeImpactAnalysis)
            .where(ChangeImpactAnalysis.fmea_id == fmea_id)
            .order_by(desc(ChangeImpactAnalysis.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._db.execute(query)
        items = list(result.scalars().all())

        responses = [ChangeImpactAnalysisResponse.model_validate(i) for i in items]
        return responses, total

    async def list_all(
        self,
        product_line_codes: list[str] | None = None,
        page: int = 1,
        page_size: int = 20,
        factory_id: uuid.UUID | None = None,
    ) -> tuple[list[ChangeImpactAnalysisResponse], int]:
        """查询所有分析记录，支持按产品线和工厂过滤（None = 不过滤）。"""
        count_stmt = select(func.count()).select_from(ChangeImpactAnalysis)
        query = select(ChangeImpactAnalysis)

        if product_line_codes is not None:
            count_stmt = count_stmt.where(
                ChangeImpactAnalysis.product_line_code.in_(product_line_codes)
            )
            query = query.where(
                ChangeImpactAnalysis.product_line_code.in_(product_line_codes)
            )

        if factory_id is not None:
            count_stmt = count_stmt.where(
                ChangeImpactAnalysis.factory_id == factory_id
            )
            query = query.where(
                ChangeImpactAnalysis.factory_id == factory_id
            )

        count_result = await self._db.execute(count_stmt)
        total = count_result.scalar() or 0

        query = (
            query.order_by(desc(ChangeImpactAnalysis.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._db.execute(query)
        items = list(result.scalars().all())

        responses = [ChangeImpactAnalysisResponse.model_validate(i) for i in items]
        return responses, total

    async def get_by_id(
        self, analysis_id: uuid.UUID
    ) -> ChangeImpactAnalysisResponse | None:
        """按 ID 查询分析详情。"""
        result = await self._db.execute(
            select(ChangeImpactAnalysis).where(ChangeImpactAnalysis.id == analysis_id)
        )
        record = result.scalar_one_or_none()
        if not record:
            return None
        return ChangeImpactAnalysisResponse.model_validate(record)
