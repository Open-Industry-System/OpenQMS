"""IQC AQL 动态调整服务 — 规则引擎 + AQL 计算 + 建议管理。

基于 ISO 2859-1 状态转移规则，结合供应商表现、SCAR/客诉等多维因素，
生成可解释的 AQL 调整建议，经工程师/经理审批后生效。
"""

import uuid
import logging
from dataclasses import dataclass
from datetime import datetime, date, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.aql_engine import AQL_VALUES
from app.models.iqc_aql_profile import IqcAqlProfile
from app.models.iqc_aql_recommendation import IqcAqlRecommendation
from app.models.iqc_aql_quality_snapshot import IqcAqlQualitySnapshot
from app.models.iqc_aql_config import IqcAqlConfig
from app.models.iqc_inspection import IqcInspection
from app.models.iqc_material import IqcMaterial
from app.models.supplier import SupplierSCAR, SupplierEvaluation
from app.models.audit import AuditLog
from app.models.user import User

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AqlContext — 规则引擎输入
# ---------------------------------------------------------------------------

@dataclass
class AqlContext:
    """规则引擎输入上下文"""
    supplier_id: uuid.UUID
    material_id: uuid.UUID
    profile_state: str
    current_aql: float
    base_aql: float
    consecutive_accepted: int
    consecutive_rejected: int
    last_30d_batch_count: int
    last_30d_ppm: float | None
    last_90d_ppm: float | None
    open_scar_count: int
    supplier_rating: str | None
    has_safety_defect: bool
    linked_customer_complaint: bool
    ppm_threshold_high: float
    ppm_threshold_low: float


# ---------------------------------------------------------------------------
# AQL 阶梯映射
# ---------------------------------------------------------------------------

def get_aql_by_state(
    base_aql: float,
    state: str,
    aql_steps: int = 0,
    current_aql: float | None = None,
    min_aql: float | None = None,
    max_aql: float | None = None,
) -> float:
    """基于基准 AQL、状态和偏移档数计算目标 AQL。

    状态映射规则（基于 ISO 2859-1 转移规则）：
    - normal:    基准 AQL（不变，aql_steps 忽略）
    - tightened: 基准 AQL 左移（减小）aql_steps 档
    - reduced:   基准 AQL 右移（增大）aql_steps 档
    - frozen:    保持 current_aql 不变（必须传入 current_aql）
    """
    if state == "frozen":
        return current_aql if current_aql is not None else base_aql

    base_idx = min(range(len(AQL_VALUES)), key=lambda i: abs(AQL_VALUES[i] - base_aql))

    if state == "normal":
        target_idx = base_idx
    elif state == "tightened":
        target_idx = max(0, base_idx - aql_steps)
    elif state == "reduced":
        target_idx = min(len(AQL_VALUES) - 1, base_idx + aql_steps)
    else:
        return base_aql

    target_aql = AQL_VALUES[target_idx]

    # 应用边界约束
    if min_aql is not None:
        target_aql = max(min_aql, target_aql)
    if max_aql is not None:
        target_aql = min(max_aql, target_aql)

    return target_aql


# ---------------------------------------------------------------------------
# 规则定义
# ---------------------------------------------------------------------------

AQL_RULES = [
    # ── 冻结规则（最高优先级）──
    {
        "id": "FREEZE_SAFETY_DEFECT",
        "category": "freeze",
        "priority": 100,
        "condition": lambda ctx: ctx.has_safety_defect,
        "target_state": "frozen",
        "frozen_reason": "safety_defect",
        "reason_cn": "发现安全/法规相关缺陷",
        "approval_level": "manager",
        "frozen_days": 90,
        "frozen_aql_policy": "tighten",  # 冻结时先加严到 tightened 档位
        "aql_steps": 1,
    },
    {
        "id": "FREEZE_SCAR_UNRESOLVED",
        "category": "freeze",
        "priority": 95,
        "condition": lambda ctx: ctx.open_scar_count > 0 and ctx.profile_state == "reduced",
        "target_state": "frozen",
        "frozen_reason": "scar_unresolved",
        "reason_cn": "SCAR未关闭期间不允许放宽",
        "approval_level": "manager",
        "frozen_days": 30,
        "frozen_aql_policy": "current",  # 冻结时保持当前 AQL 不变
        "aql_steps": 0,
    },
    # ── 加严规则 ──
    {
        "id": "TIGHTEN_CUSTOMER_COMPLAINT",
        "category": "tighten",
        "priority": 90,
        "condition": lambda ctx: ctx.linked_customer_complaint,
        "target_state": "tightened",
        "reason_cn": "关联客户投诉",
        "approval_level": "manager",
        "aql_steps": 1,
    },
    {
        "id": "TIGHTEN_2_REJECTS",
        "category": "tighten",
        "priority": 80,
        "condition": lambda ctx: ctx.consecutive_rejected >= 2,
        "target_state": "tightened",
        "reason_cn": "连续2批不合格",
        "approval_level": "manager",
        "aql_steps": 2,
    },
    {
        "id": "TIGHTEN_1_REJECT",
        "category": "tighten",
        "priority": 70,
        "condition": lambda ctx: ctx.consecutive_rejected >= 1,
        "target_state": "tightened",
        "reason_cn": "本批拒收",
        "approval_level": "manager",
        "aql_steps": 1,
    },
    {
        "id": "TIGHTEN_OPEN_SCAR",
        "category": "tighten",
        "priority": 60,
        "condition": lambda ctx: ctx.open_scar_count > 0,
        "target_state": "tightened",
        "reason_cn": "有未关闭SCAR",
        "approval_level": "manager",
        "aql_steps": 1,
    },
    {
        "id": "TIGHTEN_HIGH_PPM",
        "category": "tighten",
        "priority": 50,
        "condition": lambda ctx: ctx.last_90d_ppm is not None and ctx.last_90d_ppm > ctx.ppm_threshold_high,
        "target_state": "tightened",
        "reason_cn": "近90天PPM超过阈值",
        "approval_level": "manager",
        "aql_steps": 1,
    },
    # ── 恢复正常规则（加严后必须先恢复）──
    {
        "id": "RETURN_TO_NORMAL",
        "category": "normal",
        "priority": 30,
        "condition": lambda ctx: ctx.profile_state == "tightened" and ctx.consecutive_accepted >= 5,
        "target_state": "normal",
        "reason_cn": "加严状态下连续5批合格，恢复正常检验",
        "approval_level": "engineer",
        "aql_steps": 0,
    },
    # ── 放宽规则（最低优先级，在 normal 或已放宽状态下可触发）──
    {
        "id": "REDUCE_LEVEL_2",
        "category": "reduce",
        "priority": 20,
        "condition": lambda ctx: (
            ctx.profile_state in ("normal", "reduced")
            and ctx.consecutive_accepted >= 10
            and ctx.supplier_rating in ("A", "B")
            and (ctx.last_90d_ppm is None or ctx.last_90d_ppm < ctx.ppm_threshold_low)
            and ctx.open_scar_count == 0
            and not ctx.has_safety_defect
        ),
        "target_state": "reduced",
        "reason_cn": "正常或已放宽状态下连续10批合格，供应商评级A/B，PPM达标",
        "approval_level": "manager",
        "aql_steps": 2,
    },
    {
        "id": "REDUCE_LEVEL_1",
        "category": "reduce",
        "priority": 10,
        "condition": lambda ctx: (
            ctx.profile_state == "normal"
            and ctx.consecutive_accepted >= 5
            and ctx.open_scar_count == 0
            and not ctx.has_safety_defect
        ),
        "target_state": "reduced",
        "reason_cn": "正常状态下连续5批合格，无未关闭SCAR",
        "approval_level": "manager",
        "aql_steps": 1,
    },
]


# ---------------------------------------------------------------------------
# RuleEngine
# ---------------------------------------------------------------------------

class RuleEngine:
    """规则引擎：评估上下文，返回目标状态和建议"""

    RULES: list[dict] = AQL_RULES

    def evaluate(self, ctx: AqlContext) -> dict:
        """Evaluate rules by priority (descending), return first match or keep."""
        for rule in sorted(self.RULES, key=lambda r: -r["priority"]):
            if rule["condition"](ctx):
                return self._build_result(ctx, rule)
        return {
            "target_state": ctx.profile_state,
            "direction": "keep",
            "reason_cn": "无匹配规则，保持当前状态",
            "approval_level": "engineer",
            "aql_steps": 0,
            "frozen_aql_policy": None,
            "frozen_days": None,
            "frozen_reason": None,
            "rule_id": "KEEP",
        }

    def _build_result(self, ctx: AqlContext, rule: dict) -> dict:
        return {
            "target_state": rule["target_state"],
            "direction": rule["category"],
            "reason_cn": rule["reason_cn"],
            "approval_level": rule.get("approval_level", "engineer"),
            "aql_steps": rule.get("aql_steps", 0),
            "frozen_aql_policy": rule.get("frozen_aql_policy"),
            "frozen_days": rule.get("frozen_days"),
            "frozen_reason": rule.get("frozen_reason"),
            "rule_id": rule["id"],
        }


# ---------------------------------------------------------------------------
# AqlConfigManager
# ---------------------------------------------------------------------------

# Default config values — used when no DB row exists and for reset
DEFAULT_CONFIGS = [
    {"config_key": "consecutive_accepted_for_reduce_1", "config_value": "5", "value_type": "int", "description": "放宽一级所需连续合格批次"},
    {"config_key": "consecutive_accepted_for_reduce_2", "config_value": "10", "value_type": "int", "description": "放宽两级所需连续合格批次"},
    {"config_key": "consecutive_rejected_for_tighten_1", "config_value": "1", "value_type": "int", "description": "加严一级所需连续不合格批次"},
    {"config_key": "consecutive_rejected_for_tighten_2", "config_value": "2", "value_type": "int", "description": "加严两级所需连续不合格批次"},
    {"config_key": "ppm_threshold_high", "config_value": "5000", "value_type": "float", "description": "PPM加严阈值 (parts per million)"},
    {"config_key": "ppm_threshold_low", "config_value": "1000", "value_type": "float", "description": "PPM放宽阈值 (parts per million)"},
    {"config_key": "recommendation_expiry_days", "config_value": "7", "value_type": "int", "description": "建议过期天数"},
    {"config_key": "max_aql_default", "config_value": "2.5", "value_type": "float", "description": "默认最大AQL"},
    {"config_key": "min_aql_default", "config_value": "0.40", "value_type": "float", "description": "默认最小AQL"},
    {"config_key": "safety_defect_freeze_days", "config_value": "90", "value_type": "int", "description": "安全缺陷冻结天数"},
    {"config_key": "default_inspection_level", "config_value": "II", "value_type": "string", "description": "默认检验水平"},
    {"config_key": "default_aql_fallback", "config_value": "1.0", "value_type": "float", "description": "物料默认 AQL 为 NULL 时的回退值"},
]


class AqlConfigManager:
    """配置参数管理"""

    @staticmethod
    async def get(db: AsyncSession, key: str, product_line_code: str | None = None) -> str:
        """Get config value, trying product_line override first, then global."""
        # Try product-line-specific override
        if product_line_code:
            result = await db.execute(
                select(IqcAqlConfig.config_value).where(
                    IqcAqlConfig.config_key == key,
                    IqcAqlConfig.product_line_code == product_line_code,
                )
            )
            val = result.scalar_one_or_none()
            if val is not None:
                return val

        # Fall back to global (product_line_code IS NULL)
        result = await db.execute(
            select(IqcAqlConfig.config_value).where(
                IqcAqlConfig.config_key == key,
                IqcAqlConfig.product_line_code.is_(None),
            )
        )
        val = result.scalar_one_or_none()
        if val is not None:
            return val

        # Fall back to hardcoded default
        for cfg in DEFAULT_CONFIGS:
            if cfg["config_key"] == key:
                return cfg["config_value"]

        raise ValueError(f"Unknown config key: {key}")

    @staticmethod
    async def get_int(db: AsyncSession, key: str, product_line_code: str | None = None) -> int:
        return int(await AqlConfigManager.get(db, key, product_line_code))

    @staticmethod
    async def get_float(db: AsyncSession, key: str, product_line_code: str | None = None) -> float:
        return float(await AqlConfigManager.get(db, key, product_line_code))

    @staticmethod
    async def set(db: AsyncSession, key: str, value: str, product_line_code: str | None = None) -> IqcAqlConfig:
        """Set a config value. Creates or updates the row."""
        result = await db.execute(
            select(IqcAqlConfig).where(
                IqcAqlConfig.config_key == key,
                IqcAqlConfig.product_line_code == (product_line_code if product_line_code else None),
            )
        )
        cfg = result.scalar_one_or_none()
        if cfg:
            cfg.config_value = value
        else:
            # Determine value_type from defaults
            value_type = "string"
            for d in DEFAULT_CONFIGS:
                if d["config_key"] == key:
                    value_type = d["value_type"]
                    break
            cfg = IqcAqlConfig(
                config_key=key,
                config_value=value,
                value_type=value_type,
                product_line_code=product_line_code,
            )
            db.add(cfg)
        await db.flush()
        return cfg

    @staticmethod
    async def list_all(db: AsyncSession, product_line_code: str | None = None) -> list[IqcAqlConfig]:
        """List all configs, optionally filtered by product line."""
        q = select(IqcAqlConfig)
        if product_line_code:
            q = q.where(
                or_(
                    IqcAqlConfig.product_line_code == product_line_code,
                    IqcAqlConfig.product_line_code.is_(None),
                )
            )
        q = q.order_by(IqcAqlConfig.config_key, IqcAqlConfig.product_line_code)
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def reset_defaults(db: AsyncSession) -> list[IqcAqlConfig]:
        """Delete all config rows and re-insert defaults."""
        await db.execute(IqcAqlConfig.__table__.delete())
        await db.flush()

        configs = []
        for d in DEFAULT_CONFIGS:
            cfg = IqcAqlConfig(
                config_key=d["config_key"],
                config_value=d["config_value"],
                value_type=d["value_type"],
                description=d["description"],
                product_line_code=None,
            )
            db.add(cfg)
            configs.append(cfg)
        await db.flush()
        return configs


# ---------------------------------------------------------------------------
# QualitySnapshotCalculator
# ---------------------------------------------------------------------------

class QualitySnapshotCalculator:
    """计算 (supplier, material) 的实时质量画像"""

    @staticmethod
    async def calculate(
        db: AsyncSession,
        supplier_id: uuid.UUID,
        material_id: uuid.UUID,
        product_line_code: str | None = None,
    ) -> AqlContext:
        """Calculate quality snapshot for (supplier, material) pair."""
        now = datetime.now(timezone.utc)

        # 1. Load profile or use defaults
        profile = await ProfileManager.get_profile(db, supplier_id, material_id)
        profile_state = profile.state if profile else "normal"
        current_aql = profile.current_aql if profile else 1.0
        base_aql = profile.base_aql if profile else 1.0

        # 2. Count consecutive accepted/rejected since state_changed_at / baseline_inspection_id
        consecutive_accepted, consecutive_rejected = await QualitySnapshotCalculator._count_consecutive(
            db, supplier_id, material_id, profile
        )

        # 3. Calculate 30d/90d PPM from inspections
        last_30d_batch_count, last_30d_ppm, last_90d_ppm = await QualitySnapshotCalculator._calculate_ppm(
            db, supplier_id, material_id, now
        )

        # 4. Count open SCARs for this supplier
        scar_result = await db.execute(
            select(func.count()).where(
                SupplierSCAR.supplier_id == supplier_id,
                SupplierSCAR.status.in_(["open", "in_progress"]),
            )
        )
        open_scar_count = scar_result.scalar() or 0

        # 5. Get supplier rating (latest evaluation grade)
        eval_result = await db.execute(
            select(SupplierEvaluation.grade)
            .where(SupplierEvaluation.supplier_id == supplier_id)
            .order_by(SupplierEvaluation.created_at.desc())
            .limit(1)
        )
        supplier_rating = eval_result.scalar_one_or_none()

        # 6. Check latest inspection for safety_defect and customer_complaint
        latest_insp = await db.execute(
            select(IqcInspection)
            .where(
                IqcInspection.supplier_id == supplier_id,
                IqcInspection.material_id == material_id,
                IqcInspection.status == "judged",
            )
            .order_by(IqcInspection.judged_at.desc())
            .limit(1)
        )
        latest = latest_insp.scalar_one_or_none()
        has_safety_defect = latest.has_safety_defect if latest else False
        linked_customer_complaint = bool(latest and latest.linked_customer_complaint_id is not None)

        # 7. Get PPM thresholds from config
        ppm_threshold_high = await AqlConfigManager.get_float(db, "ppm_threshold_high", product_line_code)
        ppm_threshold_low = await AqlConfigManager.get_float(db, "ppm_threshold_low", product_line_code)

        # 8. Return AqlContext
        return AqlContext(
            supplier_id=supplier_id,
            material_id=material_id,
            profile_state=profile_state,
            current_aql=current_aql,
            base_aql=base_aql,
            consecutive_accepted=consecutive_accepted,
            consecutive_rejected=consecutive_rejected,
            last_30d_batch_count=last_30d_batch_count,
            last_30d_ppm=last_30d_ppm,
            last_90d_ppm=last_90d_ppm,
            open_scar_count=open_scar_count,
            supplier_rating=supplier_rating,
            has_safety_defect=has_safety_defect,
            linked_customer_complaint=linked_customer_complaint,
            ppm_threshold_high=ppm_threshold_high,
            ppm_threshold_low=ppm_threshold_low,
        )

    @staticmethod
    async def _count_consecutive(
        db: AsyncSession,
        supplier_id: uuid.UUID,
        material_id: uuid.UUID,
        profile: IqcAqlProfile | None,
    ) -> tuple[int, int]:
        """Count consecutive accepted/rejected since state change baseline."""
        q = (
            select(IqcInspection.inspection_result, IqcInspection.inspection_id)
            .where(
                IqcInspection.supplier_id == supplier_id,
                IqcInspection.material_id == material_id,
                IqcInspection.status == "judged",
                IqcInspection.inspection_result.in_(["accepted", "rejected"]),
            )
            .order_by(IqcInspection.judged_at.desc())
        )

        # Filter after baseline if profile has state_changed_at
        if profile and profile.state_changed_at:
            q = q.where(IqcInspection.judged_at >= profile.state_changed_at)
        if profile and profile.baseline_inspection_id:
            # Exclude the baseline inspection itself
            q = q.where(IqcInspection.inspection_id != profile.baseline_inspection_id)

        result = await db.execute(q)
        rows = result.all()

        consecutive_accepted = 0
        consecutive_rejected = 0

        # Count from most recent backwards — consecutive same-result until break
        if rows:
            first_result = rows[0][0]
            if first_result == "accepted":
                for row in rows:
                    if row[0] == "accepted":
                        consecutive_accepted += 1
                    else:
                        break
            elif first_result == "rejected":
                for row in rows:
                    if row[0] == "rejected":
                        consecutive_rejected += 1
                    else:
                        break

        return consecutive_accepted, consecutive_rejected

    @staticmethod
    async def _calculate_ppm(
        db: AsyncSession,
        supplier_id: uuid.UUID,
        material_id: uuid.UUID,
        now: datetime,
    ) -> tuple[int, float | None, float | None]:
        """Calculate batch count and PPM for 30d/90d windows."""
        # 30-day window
        d30 = now - timedelta(days=30)
        d90 = now - timedelta(days=90)

        base_filter = and_(
            IqcInspection.supplier_id == supplier_id,
            IqcInspection.material_id == material_id,
            IqcInspection.status == "judged",
        )

        # 30d batch count
        count_30_result = await db.execute(
            select(func.count()).where(base_filter, IqcInspection.judged_at >= d30)
        )
        last_30d_batch_count = count_30_result.scalar() or 0

        # 30d PPM
        last_30d_ppm = None
        if last_30d_batch_count > 0:
            rejected_30 = await db.execute(
                select(func.count()).where(
                    base_filter,
                    IqcInspection.judged_at >= d30,
                    IqcInspection.inspection_result == "rejected",
                )
            )
            rejected_30_count = rejected_30.scalar() or 0
            last_30d_ppm = (rejected_30_count / last_30d_batch_count) * 1_000_000

        # 90d PPM
        last_90d_ppm = None
        count_90_result = await db.execute(
            select(func.count()).where(base_filter, IqcInspection.judged_at >= d90)
        )
        count_90 = count_90_result.scalar() or 0
        if count_90 > 0:
            rejected_90 = await db.execute(
                select(func.count()).where(
                    base_filter,
                    IqcInspection.judged_at >= d90,
                    IqcInspection.inspection_result == "rejected",
                )
            )
            rejected_90_count = rejected_90.scalar() or 0
            last_90d_ppm = (rejected_90_count / count_90) * 1_000_000

        return last_30d_batch_count, last_30d_ppm, last_90d_ppm


# ---------------------------------------------------------------------------
# ProfileManager
# ---------------------------------------------------------------------------

class ProfileManager:
    """AQL Profile CRUD + 生效管理"""

    @staticmethod
    async def get_profile(
        db: AsyncSession, supplier_id: uuid.UUID, material_id: uuid.UUID
    ) -> IqcAqlProfile | None:
        result = await db.execute(
            select(IqcAqlProfile).where(
                IqcAqlProfile.supplier_id == supplier_id,
                IqcAqlProfile.material_id == material_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_or_create_profile(
        db: AsyncSession,
        supplier_id: uuid.UUID,
        material_id: uuid.UUID,
        product_line_code: str,
        user_id: uuid.UUID | None = None,
    ) -> IqcAqlProfile:
        """Get existing profile or create with base_aql from material.default_aql or config fallback."""
        profile = await ProfileManager.get_profile(db, supplier_id, material_id)
        if profile:
            return profile

        # Determine base_aql
        material_result = await db.execute(
            select(IqcMaterial).where(IqcMaterial.material_id == material_id)
        )
        material = material_result.scalar_one_or_none()

        if material and material.default_aql is not None:
            base_aql = material.default_aql
        else:
            base_aql = await AqlConfigManager.get_float(db, "default_aql_fallback", product_line_code)

        # Determine min_aql / max_aql defaults
        min_aql, max_aql = ProfileManager._calculate_default_bounds(base_aql)

        inspection_level = "II"
        if material and material.default_inspection_level:
            inspection_level = material.default_inspection_level

        profile = IqcAqlProfile(
            supplier_id=supplier_id,
            material_id=material_id,
            base_aql=base_aql,
            current_aql=base_aql,
            min_aql=min_aql,
            max_aql=max_aql,
            inspection_level=inspection_level,
            state="normal",
            effective_from=date.today(),
            product_line_code=product_line_code,
        )
        db.add(profile)
        await db.flush()

        db.add(AuditLog(
            table_name="iqc_aql_profiles",
            record_id=profile.profile_id,
            action="CREATE",
            changed_fields={
                "supplier_id": str(supplier_id),
                "material_id": str(material_id),
                "base_aql": base_aql,
                "current_aql": base_aql,
                "state": "normal",
            },
            operated_by=user_id,
        ))
        await db.flush()
        return profile

    @staticmethod
    def _calculate_default_bounds(base_aql: float) -> tuple[float | None, float | None]:
        """Calculate default min/max AQL bounds based on base_aql position in AQL_VALUES."""
        base_idx = min(range(len(AQL_VALUES)), key=lambda i: abs(AQL_VALUES[i] - base_aql))
        # min_aql: base_aql 左侧1档或 base_aql 本身，取更严者（数值更小）
        min_idx = max(0, base_idx - 1)
        min_aql = AQL_VALUES[min_idx] if min_idx < base_idx else base_aql
        # max_aql: base_aql 右侧2档和 2.5 的较小者
        max_idx = min(len(AQL_VALUES) - 1, base_idx + 2)
        max_aql = min(AQL_VALUES[max_idx], 2.5)
        return min_aql, max_aql

    @staticmethod
    async def apply_recommendation(
        db: AsyncSession,
        recommendation: IqcAqlRecommendation,
        inspection_id: uuid.UUID | None = None,
    ) -> IqcAqlProfile:
        """Apply approved recommendation to profile (approved -> effective)."""
        # 1. Load profile
        result = await db.execute(
            select(IqcAqlProfile).where(IqcAqlProfile.profile_id == recommendation.profile_id)
        )
        profile = result.scalar_one_or_none()
        if not profile:
            raise ValueError("AQL档案不存在")

        # 2. Record old_state
        old_state = profile.state
        old_aql = profile.current_aql

        # 3. Update profile.current_aql
        profile.current_aql = recommendation.recommended_aql

        # 4. Update profile.state from recommendation evidence
        evidence = recommendation.evidence or {}
        target_state = evidence.get("target_state", recommendation.direction)
        if target_state == "freeze":
            target_state = "frozen"
        profile.state = target_state

        # 5. If state changed: update state_changed_at, baseline_inspection_id
        if old_state != target_state:
            now = datetime.now(timezone.utc)
            profile.state_changed_at = now
            profile.baseline_inspection_id = inspection_id

        # 6. Handle frozen state
        if target_state == "frozen":
            frozen_days = evidence.get("frozen_days")
            if frozen_days:
                profile.frozen_until = date.today() + timedelta(days=frozen_days)
            profile.frozen_reason = evidence.get("frozen_reason")

        # 7. Update approved_by, approved_at, effective_from
        now = datetime.now(timezone.utc)
        profile.approved_by = recommendation.manager_decided_by or recommendation.engineer_decided_by
        profile.approved_at = now
        profile.effective_from = date.today()

        # 8. Write AuditLog
        db.add(AuditLog(
            table_name="iqc_aql_profiles",
            record_id=profile.profile_id,
            action="AQL_ADJUST",
            changed_fields={
                "old_state": old_state,
                "new_state": target_state,
                "old_aql": old_aql,
                "new_aql": recommendation.recommended_aql,
                "recommendation_id": str(recommendation.recommendation_id),
                "rule_id": evidence.get("rule_id"),
            },
            operated_by=profile.approved_by,
        ))

        # 9. Mark recommendation.status = "effective"
        recommendation.status = "effective"
        recommendation.effective_from = date.today()

        await db.flush()
        return profile


# ---------------------------------------------------------------------------
# RecommendationManager
# ---------------------------------------------------------------------------

class RecommendationManager:
    """建议生成、审批、状态管理"""

    @staticmethod
    async def generate_recommendation(
        db: AsyncSession,
        profile: IqcAqlProfile,
        ctx: AqlContext,
        rule_result: dict,
        inspection_id: uuid.UUID | None = None,
    ) -> IqcAqlRecommendation | None:
        """Generate recommendation from rule evaluation result."""
        # 1. Calculate recommended_aql using frozen_aql_policy logic
        target_state = rule_result["target_state"]
        frozen_aql_policy = rule_result.get("frozen_aql_policy")
        aql_steps = rule_result.get("aql_steps", 0)

        if target_state == "frozen" and frozen_aql_policy == "tighten":
            # 冻结时先加严到 tightened 档位
            recommended_aql = get_aql_by_state(
                profile.base_aql, "tightened", aql_steps,
                current_aql=profile.current_aql,
                min_aql=profile.min_aql, max_aql=profile.max_aql,
            )
        elif target_state == "frozen" and frozen_aql_policy == "current":
            # 冻结时保持当前 AQL 不变
            recommended_aql = profile.current_aql
        else:
            recommended_aql = get_aql_by_state(
                profile.base_aql, target_state, aql_steps,
                current_aql=profile.current_aql,
                min_aql=profile.min_aql, max_aql=profile.max_aql,
            )

        # 2. Keep check: target_state == profile.state AND recommended_aql == profile.current_aql
        if target_state == profile.state and recommended_aql == profile.current_aql:
            return None

        # 3. Dedup check: existing pending/forwarded with same profile+target_state+recommended_aql
        existing = await db.execute(
            select(func.count()).where(
                IqcAqlRecommendation.profile_id == profile.profile_id,
                IqcAqlRecommendation.status.in_(["pending", "forwarded"]),
                IqcAqlRecommendation.recommended_aql == recommended_aql,
            )
        )
        if (existing.scalar() or 0) > 0:
            return None

        # 4. Create recommendation record
        direction = rule_result["direction"]
        if direction == "normal":
            direction = "normal"  # RETURN_TO_NORMAL direction

        expiry_days = await AqlConfigManager.get_int(
            db, "recommendation_expiry_days", profile.product_line_code
        )
        now = datetime.now(timezone.utc)

        recommendation = IqcAqlRecommendation(
            profile_id=profile.profile_id,
            supplier_id=profile.supplier_id,
            material_id=profile.material_id,
            current_aql=profile.current_aql,
            recommended_aql=recommended_aql,
            direction=direction,
            trigger_rules=[{
                "rule_id": rule_result["rule_id"],
                "reason": rule_result["reason_cn"],
            }],
            evidence={
                "target_state": target_state,
                "rule_id": rule_result["rule_id"],
                "reason_cn": rule_result["reason_cn"],
                "aql_steps": aql_steps,
                "frozen_aql_policy": frozen_aql_policy,
                "frozen_days": rule_result.get("frozen_days"),
                "frozen_reason": rule_result.get("frozen_reason"),
                "consecutive_accepted": ctx.consecutive_accepted,
                "consecutive_rejected": ctx.consecutive_rejected,
                "last_30d_ppm": ctx.last_30d_ppm,
                "last_90d_ppm": ctx.last_90d_ppm,
                "open_scar_count": ctx.open_scar_count,
                "supplier_rating": ctx.supplier_rating,
                "has_safety_defect": ctx.has_safety_defect,
                "linked_customer_complaint": ctx.linked_customer_complaint,
            },
            status="pending",
            approval_level=rule_result.get("approval_level", "engineer"),
            expires_at=now + timedelta(days=expiry_days),
        )
        db.add(recommendation)

        db.add(AuditLog(
            table_name="iqc_aql_recommendations",
            record_id=recommendation.recommendation_id,
            action="AQL_REC_CREATE",
            changed_fields={
                "rule_id": rule_result["rule_id"],
                "direction": direction,
                "current_aql": profile.current_aql,
                "recommended_aql": recommended_aql,
                "target_state": target_state,
            },
        ))

        await db.flush()
        return recommendation

    @staticmethod
    async def approve(
        db: AsyncSession,
        recommendation_id: uuid.UUID,
        user_id: uuid.UUID,
        is_engineer: bool = True,
    ) -> IqcAqlRecommendation:
        """Approve recommendation.

        - Engineer can approve non-reduce recommendations directly -> auto-apply.
        - Reduce recommendations must be forwarded to manager first.
        - Manager can approve any recommendation.
        """
        rec = await RecommendationManager._get_rec(db, recommendation_id)

        if is_engineer:
            if rec.direction == "reduce":
                raise ValueError("放宽建议需提交经理审批，请使用 forward 操作")
            if rec.status != "pending":
                raise ValueError(f"当前状态 {rec.status} 不允许工程师批准")
            rec.engineer_decision = "approve"
            rec.engineer_decided_by = user_id
            rec.engineer_decided_at = datetime.now(timezone.utc)
            rec.status = "approved"
        else:
            # Manager approval
            if rec.status not in ("pending", "forwarded"):
                raise ValueError(f"当前状态 {rec.status} 不允许经理批准")
            rec.manager_decision = "approve"
            rec.manager_decided_by = user_id
            rec.manager_decided_at = datetime.now(timezone.utc)
            rec.status = "approved"

        db.add(AuditLog(
            table_name="iqc_aql_recommendations",
            record_id=recommendation_id,
            action="AQL_REC_APPROVE",
            changed_fields={
                "status": "approved",
                "approver_role": "engineer" if is_engineer else "manager",
            },
            operated_by=user_id,
        ))

        await db.flush()
        return rec

    @staticmethod
    async def reject(
        db: AsyncSession,
        recommendation_id: uuid.UUID,
        user_id: uuid.UUID,
        reason: str | None = None,
        is_engineer: bool = True,
    ) -> IqcAqlRecommendation:
        """Reject recommendation."""
        rec = await RecommendationManager._get_rec(db, recommendation_id)

        if is_engineer:
            if rec.status != "pending":
                raise ValueError(f"当前状态 {rec.status} 不允许工程师拒绝")
            rec.engineer_decision = "reject"
            rec.engineer_decided_by = user_id
            rec.engineer_decided_at = datetime.now(timezone.utc)
        else:
            if rec.status not in ("pending", "forwarded"):
                raise ValueError(f"当前状态 {rec.status} 不允许经理拒绝")
            rec.manager_decision = "reject"
            rec.manager_decided_by = user_id
            rec.manager_decided_at = datetime.now(timezone.utc)

        rec.status = "rejected"

        db.add(AuditLog(
            table_name="iqc_aql_recommendations",
            record_id=recommendation_id,
            action="AQL_REC_REJECT",
            changed_fields={"reason": reason},
            operated_by=user_id,
        ))

        await db.flush()
        return rec

    @staticmethod
    async def forward(
        db: AsyncSession,
        recommendation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> IqcAqlRecommendation:
        """Forward reduce recommendation to manager."""
        rec = await RecommendationManager._get_rec(db, recommendation_id)

        if rec.status != "pending":
            raise ValueError(f"当前状态 {rec.status} 不允许提交经理")
        if rec.direction != "reduce":
            raise ValueError("仅放宽建议需提交经理审批")

        rec.engineer_decision = "forward"
        rec.engineer_decided_by = user_id
        rec.engineer_decided_at = datetime.now(timezone.utc)
        rec.status = "forwarded"

        db.add(AuditLog(
            table_name="iqc_aql_recommendations",
            record_id=recommendation_id,
            action="AQL_REC_FWD",
            changed_fields={"status": "forwarded"},
            operated_by=user_id,
        ))

        await db.flush()
        return rec

    @staticmethod
    async def mark_expired(
        db: AsyncSession,
        recommendation_id: uuid.UUID,
    ) -> IqcAqlRecommendation:
        """Mark a single recommendation as expired."""
        rec = await RecommendationManager._get_rec(db, recommendation_id)
        if rec.status not in ("pending", "forwarded"):
            raise ValueError(f"当前状态 {rec.status} 不允许标记过期")
        rec.status = "expired"
        await db.flush()
        return rec

    @staticmethod
    async def expire_stale(db: AsyncSession) -> int:
        """Mark all pending/forwarded recommendations past expires_at as expired."""
        now = datetime.now(timezone.utc)
        result = await db.execute(
            update(IqcAqlRecommendation)
            .where(
                IqcAqlRecommendation.status.in_(["pending", "forwarded"]),
                IqcAqlRecommendation.expires_at < now,
            )
            .values(status="expired")
            .returning(IqcAqlRecommendation.recommendation_id)
        )
        expired_ids = result.fetchall()
        await db.flush()
        return len(expired_ids)

    @staticmethod
    async def _get_rec(db: AsyncSession, recommendation_id: uuid.UUID) -> IqcAqlRecommendation:
        result = await db.execute(
            select(IqcAqlRecommendation).where(
                IqcAqlRecommendation.recommendation_id == recommendation_id
            )
        )
        rec = result.scalar_one_or_none()
        if not rec:
            raise ValueError("建议记录不存在")
        return rec


# ---------------------------------------------------------------------------
# AqlService facade
# ---------------------------------------------------------------------------

class AqlService:
    """AQL 动态调整服务门面"""

    @staticmethod
    async def get_profile(
        db: AsyncSession, supplier_id: uuid.UUID, material_id: uuid.UUID
    ) -> IqcAqlProfile | None:
        return await ProfileManager.get_profile(db, supplier_id, material_id)

    @staticmethod
    async def on_inspection_judged(
        db: AsyncSession,
        supplier_id: uuid.UUID,
        material_id: uuid.UUID,
        inspection_id: uuid.UUID,
    ) -> IqcAqlRecommendation | None:
        """Trigger rule evaluation after inspection judgment."""
        # 1. Get or create profile
        # Need product_line_code — get from inspection
        insp_result = await db.execute(
            select(IqcInspection).where(IqcInspection.inspection_id == inspection_id)
        )
        inspection = insp_result.scalar_one_or_none()
        product_line_code = inspection.product_line_code if inspection else "DC-DC-100"

        profile = await ProfileManager.get_or_create_profile(
            db, supplier_id, material_id, product_line_code
        )

        # 2. Calculate quality snapshot
        ctx = await QualitySnapshotCalculator.calculate(
            db, supplier_id, material_id, product_line_code
        )

        # 3. Save snapshot to DB
        now = datetime.now(timezone.utc)
        snapshot = IqcAqlQualitySnapshot(
            supplier_id=supplier_id,
            material_id=material_id,
            inspection_id=inspection_id,
            snapshot_at=now,
            total_batches=ctx.last_30d_batch_count,
            consecutive_accepted=ctx.consecutive_accepted,
            consecutive_rejected=ctx.consecutive_rejected,
            last_30d_batch_count=ctx.last_30d_batch_count,
            last_30d_ppm=ctx.last_30d_ppm,
            last_90d_ppm=ctx.last_90d_ppm,
            open_scar_count=ctx.open_scar_count,
            supplier_rating=ctx.supplier_rating,
            has_safety_defect=ctx.has_safety_defect,
            linked_customer_complaint=ctx.linked_customer_complaint,
        )
        db.add(snapshot)

        # 4. Evaluate rules
        engine = RuleEngine()
        rule_result = engine.evaluate(ctx)

        # Update snapshot with calculated state
        snapshot.calculated_state = rule_result["target_state"]

        # 5. Generate recommendation if needed
        recommendation = await RecommendationManager.generate_recommendation(
            db, profile, ctx, rule_result, inspection_id
        )

        await db.flush()
        return recommendation

    @staticmethod
    async def expire_stale_recommendations(db: AsyncSession) -> int:
        return await RecommendationManager.expire_stale(db)
