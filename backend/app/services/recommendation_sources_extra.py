import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import distinct, func, select, text

from app.models.fmea import FMEADocument
from app.models.iqc_inspection import IqcInspection
from app.models.mes import MESEquipmentStatus, MESScrapRecord
from app.models.product_line import ProductLine
from app.models.spc import InspectionCharacteristic, SPCAlarm
from app.models.capa import CAPAEightD
from app.models.capa_lesson import CapaLessonLearned
from app.models.supplier import SupplierSCAR
from app.services import spc_service, supplier_quality_service
from app.services.embedding_provider import EmbeddingProvider
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


class MESSource:
    name = "mes"

    def __init__(self, db, embedding_provider=None):
        self.db = db

    async def should_skip(self, context: RecommendationContext) -> str | None:
        pl = context.capa_data.get("product_line_code")
        fid = context.factory_id
        since = datetime.now(timezone.utc) - timedelta(days=30)

        scrap_cnt = await self.db.scalar(
            select(func.count())
            .select_from(MESScrapRecord)
            .where(
                MESScrapRecord.product_line_code == pl,
                MESScrapRecord.factory_id == fid,
                MESScrapRecord.recorded_at >= since,
            )
        )
        equipment_cnt = await self.db.scalar(
            select(func.count())
            .select_from(MESEquipmentStatus)
            .where(
                MESEquipmentStatus.product_line_code == pl,
                MESEquipmentStatus.factory_id == fid,
                MESEquipmentStatus.downtime_reason.is_not(None),
                MESEquipmentStatus.recorded_at >= since,
            )
        )
        return "产品线暂无 MES 数据" if scrap_cnt == 0 and equipment_cnt == 0 else None

    async def retrieve(self, context: RecommendationContext) -> list[RecommendationCandidate]:
        pl = context.capa_data.get("product_line_code")
        fid = context.factory_id
        since = datetime.now(timezone.utc) - timedelta(days=30)

        scrap_records = (
            await self.db.execute(
                select(MESScrapRecord)
                .where(
                    MESScrapRecord.product_line_code == pl,
                    MESScrapRecord.factory_id == fid,
                    MESScrapRecord.recorded_at >= since,
                )
                .order_by(MESScrapRecord.recorded_at.desc())
                .limit(5)
            )
        ).scalars().all()

        equipment_records = (
            await self.db.execute(
                select(MESEquipmentStatus)
                .where(
                    MESEquipmentStatus.product_line_code == pl,
                    MESEquipmentStatus.factory_id == fid,
                    MESEquipmentStatus.downtime_reason.is_not(None),
                    MESEquipmentStatus.recorded_at >= since,
                )
                .order_by(MESEquipmentStatus.recorded_at.desc())
                .limit(5)
            )
        ).scalars().all()

        cands = []
        for record in scrap_records:
            desc = record.defect_description or record.defect_type
            cands.append(
                RecommendationCandidate(
                    source="mes",
                    content=f"MES 报废：{record.defect_type}（{record.defect_qty} 件）",
                    category=None,
                    confidence=0.5,
                    match_reason="MES 报废记录",
                    metadata={
                        "scrap_record_id": str(record.scrap_id),
                        "defect_type": record.defect_type,
                        "defect_qty": record.defect_qty,
                        "product_line_code": pl,
                        "factory_id": str(fid),
                    },
                )
            )

        for record in equipment_records:
            equipment_label = record.equipment_name or record.equipment_code
            cands.append(
                RecommendationCandidate(
                    source="mes",
                    content=f"设备停机：{equipment_label} {record.downtime_reason}",
                    category=None,
                    confidence=0.5,
                    match_reason="MES 设备停机记录",
                    metadata={
                        "equipment_id": str(record.record_id),
                        "equipment_code": record.equipment_code,
                        "downtime_reason": record.downtime_reason,
                        "product_line_code": pl,
                        "factory_id": str(fid),
                    },
                )
            )

        return cands


class SameTypeProductKBSource:
    """同类型产品 KB 召回：同 factory、同 product_type_code、跨 product_line 的 FMEA 语义搜索。"""

    name = "same_type_product_kb"

    def __init__(self, db, embedding_provider: EmbeddingProvider | None):
        self.db = db
        self.embedding = embedding_provider

    async def _resolve_product_type_code(self, context: RecommendationContext) -> str | None:
        pl_code = context.capa_data.get("product_line_code")
        fid = context.factory_id
        if not pl_code or not fid:
            return None
        result = await self.db.execute(
            select(ProductLine.product_type_code).where(
                ProductLine.code == pl_code,
                ProductLine.factory_id == fid,
            )
        )
        return result.scalar_one_or_none()

    async def should_skip(self, context: RecommendationContext) -> str | None:
        pt = await self._resolve_product_type_code(context)
        if not pt:
            return "无同类型产品 KB"
        return None

    async def retrieve(self, context: RecommendationContext) -> list[RecommendationCandidate]:
        if not self.embedding:
            return []

        # 与 SemanticSearchSource 一致：无授权产品线时直接返回空
        if context.user_product_lines == []:
            return []

        fid = context.factory_id
        if not fid:
            return []

        pl_code = context.capa_data.get("product_line_code")
        if not pl_code:
            return []

        pt = await self._resolve_product_type_code(context)
        if not pt:
            return []

        # 构造查询文本（D4 用 d2_description，D5 优先 d4_root_cause）
        if context.stage == "d4":
            query_text = context.capa_data.get("d2_description", "")
        else:
            query_text = context.capa_data.get("d4_root_cause", "")
            if not query_text:
                query_text = context.capa_data.get("d2_description", "")

        if not query_text or not query_text.strip():
            return []

        query_vector = await self.embedding.embed([query_text])
        if not query_vector:
            return []

        vec_str = "[" + ",".join(str(v) for v in query_vector[0]) + "]"
        user_pls = context.user_product_lines

        params: dict[str, Any] = {
            "query_vector": vec_str,
            "product_type_code": pt,
            "current_pl": pl_code,
            "factory_id": fid,
            "limit": 20,
        }
        pl_filter = ""
        if user_pls is not None:
            pl_filter = "AND de.product_line_code = ANY(:product_line_codes)"
            params["product_line_codes"] = user_pls

        # R16-修复：按 factory_id 收口，同时过滤 document_embeddings 与 product_lines，
        # 防止同 product_type 跨工厂串读。
        stmt = text(f"""
            SELECT de.entity_id AS fmea_id, de.node_id,
                   1 - (de.embedding <=> CAST(:query_vector AS vector)) AS similarity,
                   de.product_line_code
            FROM document_embeddings de
            JOIN product_lines pl ON de.product_line_code = pl.code
            WHERE pl.product_type_code = :product_type_code
              AND de.product_line_code != :current_pl
              AND de.entity_type = 'fmea_node'
              AND (de.metadata->>'node_type' = 'FailureCause'
                   OR de.metadata->>'node_type' = 'FailureMode')
              AND de.factory_id = :factory_id
              AND pl.factory_id = :factory_id
              {pl_filter}
            ORDER BY de.embedding <=> CAST(:query_vector AS vector)
            LIMIT :limit
        """)

        rows = await self.db.execute(stmt, params)
        raw_matches = rows.fetchall()

        # 关键修复：D4/D5 API 预加载的 fmea_docs 仅含当前 PL，跨 PL 召回时
        # 无法通过 context.fmea_docs 回溯图结构。这里直接按 fmea_id 从 DB 拉取
        # 当前工厂内的 FMEA 文档，自建 doc_map。
        fmea_ids = {str(row.fmea_id) for row in raw_matches}
        docs = (await self.db.execute(
            select(FMEADocument).where(
                FMEADocument.fmea_id.in_(fmea_ids),
                FMEADocument.factory_id == fid,
            )
        )).scalars().all()
        doc_map = {
            str(f.fmea_id): {
                "fmea_id": f.fmea_id,
                "document_no": f.document_no,
                "graph_data": f.graph_data,
                "product_line_code": f.product_line_code,
            }
            for f in docs
        }

        candidates: list[RecommendationCandidate] = []
        for row in raw_matches:
            fmea_id = str(row.fmea_id)
            node_id = row.node_id
            similarity = float(row.similarity)

            doc = doc_map.get(fmea_id)
            if not doc or not node_id:
                continue

            graph = doc["graph_data"]
            node_map = {n["id"]: n for n in graph.get("nodes", [])}
            node = node_map.get(node_id)
            if not node:
                continue

            node_type = node.get("type")
            edges = graph.get("edges", [])

            # D4: 召回 FailureCause 或 FailureMode
            if context.stage == "d4":
                if node_type == "FailureCause":
                    fm_id = None
                    fm_name = None
                    for e in edges:
                        if e["source"] == node_id and e["type"] == "CAUSE_OF":
                            parent = node_map.get(e["target"])
                            if parent and parent.get("type") == "FailureMode":
                                fm_id = parent["id"]
                                fm_name = parent.get("name")
                                break
                    candidates.append(RecommendationCandidate(
                        source="same_type_product_kb",
                        content=node.get("name", ""),
                        category=None,
                        confidence=similarity * 0.7,
                        match_reason="同类型产品 KB 相关失效原因",
                        metadata={
                            "failure_cause_node_id": node_id,
                            "failure_cause_desc": node.get("description"),
                            "failure_mode_node_id": fm_id,
                            "failure_mode_name": fm_name,
                            "fmea_id": fmea_id,
                            "fmea_document_no": doc.get("document_no"),
                            "product_line_code": doc.get("product_line_code"),
                            "product_type_code": pt,
                            "factory_id": str(fid),
                        },
                    ))
                elif node_type == "FailureMode":
                    candidates.append(RecommendationCandidate(
                        source="same_type_product_kb",
                        content=node.get("name", ""),
                        category=None,
                        confidence=similarity * 0.5,
                        match_reason="同类型产品 KB 相关失效模式",
                        metadata={
                            "failure_mode_node_id": node_id,
                            "failure_mode_name": node.get("name"),
                            "fmea_id": fmea_id,
                            "fmea_document_no": doc.get("document_no"),
                            "product_line_code": doc.get("product_line_code"),
                            "product_type_code": pt,
                            "factory_id": str(fid),
                        },
                    ))

            # D5: 只召回 FailureCause（后续交给 FMEAControlExpander）
            elif context.stage == "d5" and node_type == "FailureCause":
                fm_id = None
                fm_name = None
                for e in edges:
                    if e["source"] == node_id and e["type"] == "CAUSE_OF":
                        parent = node_map.get(e["target"])
                        if parent and parent.get("type") == "FailureMode":
                            fm_id = parent["id"]
                            fm_name = parent.get("name")
                            break
                candidates.append(RecommendationCandidate(
                    source="same_type_product_kb",
                    content=node.get("name", ""),
                    category=None,
                    confidence=similarity * 0.8,
                    match_reason="同类型产品 KB 相关失效原因",
                    metadata={
                        "failure_cause_node_id": node_id,
                        "failure_cause_desc": node.get("description"),
                        "failure_mode_node_id": fm_id,
                        "failure_mode_name": fm_name,
                        "fmea_id": fmea_id,
                        "fmea_document_no": doc.get("document_no"),
                        "product_line_code": doc.get("product_line_code"),
                        "product_type_code": pt,
                        "factory_id": str(fid),
                    },
                ))

        return candidates


class LessonsLearnedSource:
    """经验教训库语义召回：按 factory + 产品线权限检索 capa_lessons_learned。"""

    name = "lessons_learned"

    def __init__(self, db, embedding_provider: EmbeddingProvider | None):
        self.db = db
        self.embedding = embedding_provider

    async def should_skip(self, context: RecommendationContext) -> str | None:
        if self.embedding is None:
            return "未配置 embedding"
        fid = context.factory_id
        if not fid:
            return "无经验教训库数据"
        # R16-修复：三表 factory_id 过滤，但 should_skip 仅数 lesson 表即可（NOT NULL factory_id）
        cnt = await self.db.scalar(
            select(func.count())
            .select_from(CapaLessonLearned)
            .where(CapaLessonLearned.factory_id == fid)
        )
        return "无经验教训库数据" if cnt == 0 else None

    async def retrieve(self, context: RecommendationContext) -> list[RecommendationCandidate]:
        if not self.embedding:
            return []

        if context.user_product_lines == []:
            return []

        fid = context.factory_id
        if not fid:
            return []

        # 构造查询文本：D4 用 d2_description；D5 优先 d4_root_cause，fallback d2_description
        if context.stage == "d4":
            query_text = context.capa_data.get("d2_description", "")
        else:
            query_text = context.capa_data.get("d4_root_cause", "")
            if not query_text:
                query_text = context.capa_data.get("d2_description", "")

        if not query_text or not query_text.strip():
            return []

        query_vector = await self.embedding.embed([query_text])
        if not query_vector:
            return []

        vec_str = "[" + ",".join(str(v) for v in query_vector[0]) + "]"
        user_pls = context.user_product_lines

        params: dict[str, Any] = {
            "query_vector": vec_str,
            "factory_id": fid,
            "limit": 20,
        }
        pl_filter = ""
        if user_pls is not None:
            pl_filter = "AND de.product_line_code = ANY(:product_line_codes)"
            params["product_line_codes"] = user_pls

        # R15-修复：JOIN capa_eightd 取 source_capa_document_no（lesson 表无 document_no）
        # R16-修复：三表 factory_id 过滤（de + lesson + capa），防止孤儿/跨工厂串读
        stmt = text(f"""
            SELECT de.entity_id AS lesson_id, de.chunk_text,
                   1 - (de.embedding <=> CAST(:query_vector AS vector)) AS similarity,
                   lesson.lesson_text, lesson.category, lesson.capa_id, lesson.product_line_code,
                   capa.document_no AS source_capa_document_no
            FROM document_embeddings de
            JOIN capa_lessons_learned lesson ON de.entity_id = lesson.lesson_id
            JOIN capa_eightd capa ON lesson.capa_id = capa.report_id AND capa.factory_id = lesson.factory_id
            WHERE de.entity_type = 'capa_lesson'
              AND de.entity_field = 'lesson_text'
              AND lesson.lesson_id IS NOT NULL
              AND de.factory_id = :factory_id
              AND lesson.factory_id = :factory_id
              AND capa.factory_id = :factory_id
              {pl_filter}
            ORDER BY de.embedding <=> CAST(:query_vector AS vector)
            LIMIT :limit
        """)

        rows = await self.db.execute(stmt, params)
        candidates: list[RecommendationCandidate] = []
        for row in rows.fetchall():
            lesson_text = row.lesson_text or row.chunk_text or ""
            category = row.category
            source_capa_id = row.capa_id
            source_capa_document_no = row.source_capa_document_no
            lesson_id = row.lesson_id
            similarity = float(row.similarity)
            confidence = min(similarity * 0.8, 0.8)

            candidates.append(
                RecommendationCandidate(
                    source="lessons_learned",
                    content=f"经验教训：{lesson_text}（来自 {source_capa_document_no}，类别 {category}）",
                    category=None,
                    confidence=confidence,
                    match_reason="经验教训库相似命中",
                    metadata={
                        "source_capa_id": str(source_capa_id),
                        "source_capa_document_no": source_capa_document_no,
                        "lesson_id": str(lesson_id),
                        "category": category,
                        "product_line_code": row.product_line_code,
                        "factory_id": str(fid),
                    },
                )
            )
        return candidates
