"""
Seed script: creates demo data for development.
Run: docker compose exec backend python -m app.seed
"""
import asyncio
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from random import Random

from sqlalchemy import func, select, text

from app.config import SYSTEM_USER_ID
from app.core.security import hash_password
from app.database import async_session
from app.models.capa import CAPAEightD
from app.models.customer_quality import Customer, CustomerComplaint, RMARecord, ShipmentRecord, WarrantyRecord
from app.models.factory import Factory, UserFactory
from app.models.fmea import FMEADocument
from app.models.management_review import ManagementReview, ReviewOutput
from app.models.role import RoleDefinition, UserProductLine
from app.models.user import User

SAMPLE_GRAPH = {
    "nodes": [
        {"id": "pi_1", "type": "ProcessItem", "name": "SMT焊接生产线", "severity": 0, "occurrence": 0, "detection": 0},
        {"id": "ps_1", "type": "ProcessStep", "name": "SMT元器件贴装", "process_number": "OP10", "severity": 0, "occurrence": 0, "detection": 0},
        {"id": "we_1", "type": "ProcessWorkElement", "name": "高速贴片机", "severity": 0, "occurrence": 0, "detection": 0},
        {"id": "pif_1", "type": "ProcessItemFunction", "name": "完成电路板SMT焊接与元器件组装", "severity": 0, "occurrence": 0, "detection": 0},
        {"id": "psf_1", "type": "ProcessStepFunction", "name": "准确贴装电子元器件", "specification": "元器件贴装偏移度 <= 0.05mm", "classification": "CC", "severity": 0, "occurrence": 0, "detection": 0},
        {"id": "wef_1", "type": "ProcessWorkElementFunction", "name": "设备提供适宜且稳定的贴装压力", "requirement": "贴装压力 3.0±0.5N", "classification": "SC", "severity": 0, "occurrence": 0, "detection": 0},
        {"id": "fe_1", "type": "FailureEffect", "name": "电控板功能丧失，导致整车无法启动报警", "severity": 8, "severity_plant": 4, "severity_customer": 8, "severity_user": 8, "occurrence": 0, "detection": 0},
        {"id": "fm_1", "type": "FailureMode", "name": "元器件贴装偏移", "severity": 0, "occurrence": 0, "detection": 0},
        {"id": "fm-cc-001", "type": "FailureMode", "name": "空载转速偏差超出规格", "severity": 9, "occurrence": 3, "detection": 4},
        {"id": "fm-sc-001", "type": "FailureMode", "name": "压装扭矩不稳定", "severity": 6, "occurrence": 4, "detection": 3},
        {"id": "fc_1", "type": "FailureCause", "name": "贴装吸嘴磨损导致压力设定偏小", "severity": 0, "occurrence": 4, "detection": 0},
        {"id": "pc_1", "type": "PreventionControl", "name": "开机吸嘴压力自动零点校准与设备预防性维护", "severity": 0, "occurrence": 0, "detection": 0},
        {"id": "dc_1", "type": "DetectionControl", "name": "贴装后在线 3D-AOI 光学检测仪", "severity": 0, "occurrence": 0, "detection": 3},
        {
            "id": "ra_1",
            "type": "RecommendedAction",
            "name": "引入吸嘴压力闭环传感器进行实时监测与自适应补偿",
            "responsible": "张工",
            "due_date": "2026-06-15",
            "status": "open",
            "action_taken": "",
            "completion_date": "",
            "severity": 0,
            "occurrence": 0,
            "detection": 0,
            "revised_severity": 0,
            "revised_occurrence": 0,
            "revised_detection": 0,
            "revised_ap": ""
        }
    ],
    "edges": [
        {"source": "pi_1", "target": "ps_1", "type": "HAS_PROCESS_STEP"},
        {"source": "ps_1", "target": "we_1", "type": "HAS_WORK_ELEMENT"},
        {"source": "pi_1", "target": "pif_1", "type": "HAS_FUNCTION"},
        {"source": "ps_1", "target": "psf_1", "type": "HAS_FUNCTION"},
        {"source": "we_1", "target": "wef_1", "type": "HAS_FUNCTION"},
        {"source": "pif_1", "target": "psf_1", "type": "FUNCTION_MAPPED_TO"},
        {"source": "psf_1", "target": "wef_1", "type": "FUNCTION_MAPPED_TO"},
        {"source": "psf_1", "target": "fm_1", "type": "HAS_FAILURE_MODE"},
        {"source": "fm_1", "target": "fe_1", "type": "EFFECT_OF"},
        {"source": "fc_1", "target": "fm_1", "type": "CAUSE_OF"},
        {"source": "fc_1", "target": "pc_1", "type": "PREVENTED_BY"},
        {"source": "fc_1", "target": "dc_1", "type": "DETECTED_BY"},
        {"source": "fc_1", "target": "ra_1", "type": "OPTIMIZED_BY"},
        {"source": "psf_1", "target": "fm-cc-001", "type": "HAS_FAILURE_MODE"},
        {"source": "wef_1", "target": "fm-sc-001", "type": "HAS_FAILURE_MODE"}
    ]
}


SAMPLE_DFMEA_GRAPH = {
    "nodes": [
        {"id": "sys_1", "type": "System", "name": "电池管理系统 (BMS)", "severity": 0, "occurrence": 0, "detection": 0},
        {"id": "sub_1", "type": "Subsystem", "name": "电池监控单元 (BMU)", "severity": 0, "occurrence": 0, "detection": 0},
        {"id": "sub_2", "type": "Subsystem", "name": "热管理系统 (TMS)", "severity": 0, "occurrence": 0, "detection": 0},
        {"id": "cmp_1", "type": "Component", "name": "电压采集芯片 LTC6811", "severity": 0, "occurrence": 0, "detection": 0},
        {"id": "cmp_2", "type": "Component", "name": "NTC 温度传感器", "severity": 0, "occurrence": 0, "detection": 0},
        {"id": "sf_1", "type": "ProcessStepFunction", "name": "实时采集单体电池电压与温度", "specification": "电压精度 ±5mV, 温度精度 ±1°C", "requirement": "每 100ms 完成一轮全电芯扫描", "severity": 0, "occurrence": 0, "detection": 0},
        {"id": "cf_1", "type": "ProcessWorkElementFunction", "name": "LTC6811 提供 12通道 16bit ADC 采样", "requirement": "采样噪声 ≤ 0.5mV RMS, 通道间隔离度 ≥ 80dB", "severity": 0, "occurrence": 0, "detection": 0},
        {"id": "dfe_1", "type": "FailureEffect", "name": "电池过充/过放未被检测，导致电芯热失控起火", "severity": 10, "severity_plant": 8, "severity_customer": 10, "severity_user": 10, "occurrence": 0, "detection": 0},
        {"id": "dfm_1", "type": "FailureMode", "name": "电压采集通道漂移导致读取值偏离真实值", "severity": 0, "occurrence": 0, "detection": 0},
        {"id": "dfc_1", "type": "FailureCause", "name": "LTC6811 参考电压源温漂超出 datasheet 规格", "severity": 0, "occurrence": 5, "detection": 0},
        {"id": "dfc_2", "type": "FailureCause", "name": "PCB 布局不当导致采样回路引入共模噪声", "severity": 0, "occurrence": 3, "detection": 0},
        {"id": "dpc_1", "type": "PreventionControl", "name": "ADC 参考电压选用 AEC-Q100 Grade 0 认证芯片，温漂 ≤ 10ppm/°C", "severity": 0, "occurrence": 0, "detection": 0},
        {"id": "ddc_1", "type": "DetectionControl", "name": "BMS 上电自检：注入已知校准电压验证 ADC 通道偏差 ≤ ±3mV", "severity": 0, "occurrence": 0, "detection": 4},
        {"id": "ddc_2", "type": "DetectionControl", "name": "相邻电芯电压交叉比对：同一模组内最大压差 ≥ 50mV 触发报警", "severity": 0, "occurrence": 0, "detection": 5},
        {
            "id": "dra_1",
            "type": "RecommendedAction",
            "name": "引入独立 VREF 校准通道，BMS 每次唤醒后执行全量程三点校准",
            "responsible": "李工",
            "due_date": "2026-07-30",
            "status": "in_progress",
            "action_taken": "已完成方案设计与仿真验证，PCB layout 阶段",
            "completion_date": "",
            "severity": 0,
            "occurrence": 0,
            "detection": 0,
            "revised_severity": 10,
            "revised_occurrence": 3,
            "revised_detection": 2,
            "revised_ap": "H"
        }
    ],
    "edges": [
        {"source": "sys_1", "target": "sub_1", "type": "HAS_PROCESS_STEP"},
        {"source": "sys_1", "target": "sub_2", "type": "HAS_PROCESS_STEP"},
        {"source": "sub_1", "target": "cmp_1", "type": "HAS_WORK_ELEMENT"},
        {"source": "sub_2", "target": "cmp_2", "type": "HAS_WORK_ELEMENT"},
        {"source": "sub_1", "target": "sf_1", "type": "HAS_FUNCTION"},
        {"source": "cmp_1", "target": "cf_1", "type": "HAS_FUNCTION"},
        {"source": "sf_1", "target": "cf_1", "type": "FUNCTION_MAPPED_TO"},
        {"source": "sf_1", "target": "dfm_1", "type": "HAS_FAILURE_MODE"},
        {"source": "dfm_1", "target": "dfe_1", "type": "EFFECT_OF"},
        {"source": "dfc_1", "target": "dfm_1", "type": "CAUSE_OF"},
        {"source": "dfc_2", "target": "dfm_1", "type": "CAUSE_OF"},
        {"source": "dfc_1", "target": "dpc_1", "type": "PREVENTED_BY"},
        {"source": "dfc_1", "target": "ddc_1", "type": "DETECTED_BY"},
        {"source": "dfm_1", "target": "ddc_2", "type": "DETECTED_BY"},
        {"source": "dfc_1", "target": "dra_1", "type": "OPTIMIZED_BY"}
    ]
}


async def seed_supplier_risk_configs(db):
    """Seed default supplier risk rule configs if not present."""
    from sqlalchemy import select

    from app.models.supplier_risk import SupplierRiskConfig
    from app.models.user import User

    admin = (await db.execute(select(User).where(User.username == "admin"))).scalar_one_or_none()
    if not admin:
        return

    DEFAULT_CONFIGS = [
        {"rule_id": "R01", "enabled": True, "category": "quality", "weight": 15.0,
         "thresholds": {"ppm_limit": 1000, "window_days": 90}},
        {"rule_id": "R02", "enabled": True, "category": "quality", "weight": 12.0,
         "thresholds": {"acceptance_rate_min": 0.9, "decline_ratio": 0.1, "window_days": 90, "compare_window_days": 180}},
        {"rule_id": "R03", "enabled": True, "category": "quality", "weight": 18.0,
         "thresholds": {"consecutive_batches": 3, "batch_limit": 10}},
        {"rule_id": "R04", "enabled": True, "category": "quality", "weight": 10.0,
         "thresholds": {"open_days_limit": 30}},
        {"rule_id": "R05", "enabled": True, "category": "quality", "weight": 12.0,
         "thresholds": {"scar_count_limit": 3, "window_days": 90}},
        {"rule_id": "R06", "enabled": True, "category": "delivery", "weight": 12.0,
         "thresholds": {"delivery_score_min": 70, "decline_ratio": 0.15}},
        {"rule_id": "R07", "enabled": True, "category": "delivery", "weight": 10.0,
         "thresholds": {"from_grades": ["A", "B"], "to_grades": ["C", "D"]}},
        {"rule_id": "R08", "enabled": True, "category": "compliance", "weight": 8.0,
         "thresholds": {"warning_days": [90, 60, 30]}},
        {"rule_id": "R09", "enabled": True, "category": "compliance", "weight": 8.0,
         "thresholds": {"score_decline_limit": 15}},
        {"rule_id": "R10", "enabled": True, "category": "compliance", "weight": 15.0,
         "thresholds": {"keywords": ["安全", "安全特性", "safety"]}},
    ]

    for cfg in DEFAULT_CONFIGS:
        existing = (await db.execute(
            select(SupplierRiskConfig).where(
                SupplierRiskConfig.rule_id == cfg["rule_id"],
                SupplierRiskConfig.supplier_id.is_(None),
                SupplierRiskConfig.product_line_code.is_(None),
            )
        )).scalar_one_or_none()
        if not existing:
            db.add(SupplierRiskConfig(
                rule_id=cfg["rule_id"],
                enabled=cfg["enabled"],
                category=cfg["category"],
                weight=cfg["weight"],
                thresholds=cfg["thresholds"],
                updated_by=admin.user_id,
            ))
    await db.commit()


async def seed_supply_chain_risk_snapshots(db):
    """Seed sample risk map snapshots for 3 suppliers across 3 months."""
    from app.models.supplier import Supplier
    from app.models.supply_chain_risk_map import SupplyChainRiskSnapshot

    # Check if already seeded
    existing = await db.execute(
        select(SupplyChainRiskSnapshot).limit(1)
    )
    if existing.scalar_one_or_none():
        return

    # Fetch existing suppliers (already seeded by main seed function)
    supplier_result = await db.execute(select(Supplier).limit(3))
    suppliers = supplier_result.scalars().all()
    if len(suppliers) < 3:
        print("Not enough suppliers to seed risk map snapshots, skipping.")
        return

    periods = ["2026-01", "2026-02", "2026-03"]
    profiles = [
        {"quality": 12, "delivery": 18, "compliance": 8, "erp_ontime": 95, "scar": 0, "ppm": 500, "risk": 15, "level": "low"},
        {"quality": 45, "delivery": 55, "compliance": 30, "erp_ontime": 78, "scar": 2, "ppm": 8000, "risk": 48, "level": "medium"},
        {"quality": 72, "delivery": 80, "compliance": 65, "erp_ontime": 55, "scar": 5, "ppm": 35000, "risk": 76, "level": "high"},
    ]

    for supplier, profile in zip(suppliers[:3], profiles, strict=False):
        for i, period in enumerate(periods):
            factor = 1 + i * 0.08
            snap = SupplyChainRiskSnapshot(
                supplier_id=supplier.supplier_id,
                product_line_code=None,
                snapshot_period=period,
                risk_score=round(profile["risk"] * factor, 1),
                risk_level="high" if profile["risk"] * factor > 60 else "medium" if profile["risk"] * factor > 30 else "low",
                quality_score=round(profile["quality"] * factor, 1),
                delivery_score=round(profile["delivery"] * factor, 1),
                compliance_score=round(profile["compliance"] * factor, 1),
                erp_on_time_rate=round(max(profile["erp_ontime"] - i * 3, 0), 1),
                purchase_amount_pct=round(33.3, 1),
                open_scar_count=profile["scar"] + i,
                ppm_value=round(profile["ppm"] * factor),
                dimensions={},
            )
            db.add(snap)

    await db.flush()
    print("Seeded supply chain risk map snapshots.")


async def seed_erp_permissions(db):
    from sqlalchemy import select

    from app.models.role import RolePermission

    result = await db.execute(select(RoleDefinition))
    roles = result.scalars().all()
    for role in roles:
        level = {"admin": 5, "manager": 4, "field_qe": 2, "viewer": 1}.get(role.role_key, 1)
        existing = await db.execute(
            select(RolePermission).where(
                RolePermission.role_id == role.id,
                RolePermission.module == "erp"
            )
        )
        if not existing.scalar_one_or_none():
            db.add(RolePermission(role_id=role.id, module="erp", permission_level=level))


# Full permission matrix (mirrors alembic/028_permission_matrix.py)
_MODULES = [
    "fmea", "capa", "dashboard", "audit", "customer_quality", "customer_audit",
    "supplier", "iqc", "ppap", "spc", "msa", "planning", "management_review",
    "user_mgmt", "permission_mgmt", "special_characteristic", "quality_goal", "scar",
    "knowledge_graph", "mes", "plm", "erp", "supplier_risk", "supply_chain_risk_map",
    "group",
]

PERMISSION_MATRIX = {
    "admin": {m: 5 for m in _MODULES},
    "manager": {
        "fmea": 4, "capa": 4, "dashboard": 4, "audit": 4,
        "customer_quality": 4, "customer_audit": 4, "supplier": 4,
        "iqc": 4, "ppap": 4, "spc": 4, "msa": 4, "planning": 4,
        "management_review": 4, "user_mgmt": 1, "permission_mgmt": 0,
        "special_characteristic": 4, "quality_goal": 4, "scar": 4,
        "knowledge_graph": 3, "mes": 3, "plm": 3, "erp": 4,
        "supplier_risk": 3, "supply_chain_risk_map": 3, "group": 3,
    },
    "viewer": {
        "fmea": 1, "capa": 1, "dashboard": 1, "audit": 1,
        "customer_quality": 1, "customer_audit": 1, "supplier": 1,
        "iqc": 1, "ppap": 1, "spc": 1, "msa": 1, "planning": 1,
        "management_review": 1, "user_mgmt": 0, "permission_mgmt": 0,
        "special_characteristic": 1, "quality_goal": 1, "scar": 1,
        "knowledge_graph": 1, "mes": 1, "plm": 1, "erp": 1,
        "supplier_risk": 1, "supply_chain_risk_map": 1, "group": 1,
    },
    "customer_qe": {
        "fmea": 1, "capa": 2, "dashboard": 1, "audit": 1,
        "customer_quality": 3, "customer_audit": 3, "supplier": 1,
        "iqc": 0, "ppap": 0, "spc": 1, "msa": 0, "planning": 0,
        "management_review": 0, "user_mgmt": 0, "permission_mgmt": 0,
        "special_characteristic": 0, "quality_goal": 0, "scar": 1,
        "knowledge_graph": 0, "mes": 0, "plm": 0, "erp": 1,
        "supplier_risk": 1, "supply_chain_risk_map": 1, "group": 1,
    },
    "supplier_qe": {
        "fmea": 1, "capa": 2, "dashboard": 1, "audit": 1,
        "customer_quality": 0, "customer_audit": 0, "supplier": 3,
        "iqc": 3, "ppap": 3, "spc": 1, "msa": 0, "planning": 1,
        "management_review": 0, "user_mgmt": 0, "permission_mgmt": 0,
        "special_characteristic": 0, "quality_goal": 0, "scar": 3,
        "knowledge_graph": 0, "mes": 1, "plm": 1, "erp": 1,
        "supplier_risk": 3, "supply_chain_risk_map": 3, "group": 1,
    },
    "field_qe": {
        "fmea": 3, "capa": 3, "dashboard": 1, "audit": 1,
        "customer_quality": 1, "customer_audit": 1, "supplier": 1,
        "iqc": 1, "ppap": 0, "spc": 3, "msa": 3, "planning": 1,
        "management_review": 1, "user_mgmt": 0, "permission_mgmt": 0,
        "special_characteristic": 0, "quality_goal": 0, "scar": 1,
        "knowledge_graph": 1, "mes": 2, "plm": 1, "erp": 2,
        "supplier_risk": 1, "supply_chain_risk_map": 1, "group": 1,
    },
    "planning_qe": {
        "fmea": 3, "capa": 1, "dashboard": 1, "audit": 1,
        "customer_quality": 1, "customer_audit": 1, "supplier": 1,
        "iqc": 1, "ppap": 3, "spc": 1, "msa": 0, "planning": 3,
        "management_review": 1, "user_mgmt": 0, "permission_mgmt": 0,
        "special_characteristic": 3, "quality_goal": 0, "scar": 1,
        "knowledge_graph": 0, "mes": 1, "plm": 3, "erp": 1,
        "supplier_risk": 1, "supply_chain_risk_map": 1, "group": 1,
    },
}


async def seed_all_permissions(db):
    """Seed the full permission matrix if role_permissions is empty or incomplete."""
    from sqlalchemy import select

    from app.models.role import RolePermission

    # Check if permissions already exist
    count_result = await db.execute(
        select(func.count()).select_from(RolePermission)
    )
    existing_count = count_result.scalar() or 0
    expected_count = len(PERMISSION_MATRIX) * len(_MODULES)  # 7 * 25 = 175
    if existing_count >= expected_count:
        return  # Already seeded

    result = await db.execute(select(RoleDefinition))
    roles_map = {r.role_key: r.id for r in result.scalars().all()}

    for role_key, perms in PERMISSION_MATRIX.items():
        if role_key not in roles_map:
            continue
        role_id = roles_map[role_key]
        for module, level in perms.items():
            existing = await db.execute(
                select(RolePermission).where(
                    RolePermission.role_id == role_id,
                    RolePermission.module == module,
                )
            )
            if not existing.scalar_one_or_none():
                db.add(RolePermission(
                    role_id=role_id, module=module, permission_level=level
                ))

    await db.flush()
    print("Seeded full permission matrix.")


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2 seed data: Gauges, SPC, MSA, IQC, Control Plans, Audits, PPAP,
# Quality Goals, SCAR, MES, ERP, APQP
# ═══════════════════════════════════════════════════════════════════════════

_RNG = Random(42)  # deterministic for reproducibility


async def seed_gauges(db, admin_id, default_factory_id):
    """Seed gauge master data and calibration records."""
    from app.models.gauge import Gauge, GaugeCalibration

    existing = await db.execute(select(Gauge).where(Gauge.gauge_no == "G-001"))
    if existing.scalar_one_or_none():
        # Data already seeded, return existing gauges for downstream MSA seed
        gauges = list((await db.execute(
            select(Gauge).order_by(Gauge.gauge_no)
        )).scalars().all())
        print("Gauges already seeded, returning existing gauges.")
        return gauges

    gauges = [
        Gauge(
            gauge_no="G-001", name="数显千分尺", model="MDC-1", manufacturer="三丰",
            resolution=0.001, measuring_range="0-25mm", department="质量部",
            location="IQC检验室", status="active", calibration_cycle_days=365,
            next_calibration_date=date(2027, 5, 15),
            product_line_code="DC-DC-100", factory_id=default_factory_id,
            created_by=admin_id,
        ),
        Gauge(
            gauge_no="G-002", name="游标卡尺", model="CD-6", manufacturer="三丰",
            resolution=0.02, measuring_range="0-150mm", department="质量部",
            location="SPC测量站", status="active", calibration_cycle_days=180,
            next_calibration_date=date(2026, 11, 20),
            product_line_code="DC-DC-100", factory_id=default_factory_id,
            created_by=admin_id,
        ),
        Gauge(
            gauge_no="G-003", name="高度尺", model="192-611", manufacturer="三丰",
            resolution=0.01, measuring_range="0-300mm", department="质量部",
            location="计量室", status="active", calibration_cycle_days=365,
            next_calibration_date=date(2027, 3, 10),
            product_line_code="DC-DC-100", factory_id=default_factory_id,
            created_by=admin_id,
        ),
        Gauge(
            gauge_no="G-004", name="推拉力计", model="DS2-110N", manufacturer="IMADA",
            resolution=0.01, measuring_range="0-110N", department="质量部",
            location="装配线工位", status="active", calibration_cycle_days=365,
            next_calibration_date=date(2027, 1, 5),
            product_line_code="DC-DC-100", factory_id=default_factory_id,
            created_by=admin_id,
        ),
        Gauge(
            gauge_no="G-005", name="数字万用表", model="Fluke 87V", manufacturer="Fluke",
            resolution=0.001, measuring_range="0-1000V", department="电气检验组",
            location="电气检验室", status="active", calibration_cycle_days=365,
            next_calibration_date=date(2026, 12, 1),
            product_line_code="DC-DC-100", factory_id=default_factory_id,
            created_by=admin_id,
        ),
        Gauge(
            gauge_no="G-006", name="LCR电桥", model="IM3536", manufacturer="日置",
            resolution=0.0001, measuring_range="0.01mΩ-100MΩ", department="电气检验组",
            location="电气检验室", status="calibration_due", calibration_cycle_days=180,
            next_calibration_date=date(2026, 6, 5),
            product_line_code="DC-DC-100", factory_id=default_factory_id,
            created_by=admin_id,
        ),
    ]
    db.add_all(gauges)
    await db.flush()

    # Gauge calibrations
    calibrations = [
        GaugeCalibration(
            gauge_id=gauges[0].gauge_id, factory_id=default_factory_id,
            calibration_date=date(2026, 5, 15), result="pass",
            certificate_no="CAL-2026-001", calibrated_by="市计量院",
            notes="千分尺校准合格，偏差在允许范围内",
            next_calibration_date=date(2027, 5, 15),
        ),
        GaugeCalibration(
            gauge_id=gauges[1].gauge_id, factory_id=default_factory_id,
            calibration_date=date(2025, 11, 20), result="pass",
            certificate_no="CAL-2025-008", calibrated_by="省计量院",
            notes="卡尺校准合格",
            next_calibration_date=date(2026, 11, 20),
        ),
        GaugeCalibration(
            gauge_id=gauges[5].gauge_id, factory_id=default_factory_id,
            calibration_date=date(2025, 12, 5), result="pass",
            certificate_no="CAL-2025-012", calibrated_by="市计量院",
            notes="LCR电桥校准合格，下次需在2026年6月前完成",
            next_calibration_date=date(2026, 6, 5),
        ),
    ]
    db.add_all(calibrations)
    await db.flush()
    print("Seeded gauges and calibrations.")
    return gauges


async def seed_spc(db, admin_id, engineer_id, default_factory_id, fmea1_id, capa1_id):
    """Seed SPC inspection characteristics, sample data, and control limits."""
    from app.models.spc import InspectionCharacteristic, SampleBatch, SampleValue, ControlLimitSnapshot

    existing = await db.execute(select(InspectionCharacteristic).where(InspectionCharacteristic.ic_code == "SPC-001"))
    if existing.scalar_one_or_none():
        # Data already seeded, return existing chars for downstream MSA seed
        chars = list((await db.execute(
            select(InspectionCharacteristic).where(InspectionCharacteristic.ic_code.in_(["SPC-001", "SPC-002", "SPC-003", "SPC-004"]))
        )).scalars().all())
        print("SPC data already seeded, returning existing characteristics.")
        return chars

    rng = Random(42)

    # ── SPC Characteristics ──
    chars = [
        InspectionCharacteristic(
            ic_code="SPC-001", product_line="DC-DC-100", factory_id=default_factory_id,
            process_name="SMT贴装", characteristic_name="元器件贴装偏移度",
            spec_upper=Decimal("0.05"), spec_lower=Decimal("0"),
            target_value=Decimal("0.025"), chart_type="xbar_r", subgroup_size=5,
            created_by_id=admin_id,
        ),
        InspectionCharacteristic(
            ic_code="SPC-002", product_line="DC-DC-100", factory_id=default_factory_id,
            process_name="回流焊接", characteristic_name="焊接温度",
            spec_upper=Decimal("255"), spec_lower=Decimal("235"),
            target_value=Decimal("245"), chart_type="xbar_r", subgroup_size=5,
            created_by_id=admin_id,
        ),
        InspectionCharacteristic(
            ic_code="SPC-003", product_line="DC-DC-100", factory_id=default_factory_id,
            process_name="功能测试", characteristic_name="输出电压",
            spec_upper=Decimal("12.6"), spec_lower=Decimal("11.4"),
            target_value=Decimal("12.0"), chart_type="xbar_r", subgroup_size=5,
            created_by_id=admin_id,
        ),
        InspectionCharacteristic(
            ic_code="SPC-004", product_line="DC-DC-100", factory_id=default_factory_id,
            process_name="终检", characteristic_name="外观不良率",
            spec_upper=Decimal("3.0"), spec_lower=Decimal("0"),
            target_value=Decimal("0.5"), chart_type="p", subgroup_size=50,
            created_by_id=admin_id,
        ),
    ]
    db.add_all(chars)
    await db.flush()

    # ── Sample Batches & Values for SPC-001 ──
    now = datetime.now(UTC)
    batches_001 = []
    for i in range(25):
        b = SampleBatch(
            ic_id=chars[0].ic_id, batch_no=f"B-001-{i+1:03d}",
            factory_id=default_factory_id,
            sampled_at=now - timedelta(days=25 - i),
            subgroup_size=5,
        )
        db.add(b)
        batches_001.append(b)
    await db.flush()

    # Generate sample values around target with slight drift
    for i, b in enumerate(batches_001):
        for j in range(5):
            drift = i * 0.0002  # slight upward drift
            val = round(Decimal(str(0.025 + drift + rng.gauss(0, 0.005))), 4)
            db.add(SampleValue(
                batch_id=b.batch_id, factory_id=default_factory_id,
                sequence_no=j + 1, value=val, alarm_flags=[],
            ))
    await db.flush()

    # Control limits for SPC-001
    db.add(ControlLimitSnapshot(
        ic_id=chars[0].ic_id, factory_id=default_factory_id,
        ucl=Decimal("0.0410"), lcl=Decimal("0.0090"), cl=Decimal("0.0250"),
        r_ucl=Decimal("0.0240"), r_lcl=Decimal("0"), r_cl=Decimal("0.0120"),
        is_locked=False, version_no=1, is_active=True,
    ))

    # ── Sample Batches & Values for SPC-002 ──
    batches_002 = []
    for i in range(25):
        b = SampleBatch(
            ic_id=chars[1].ic_id, batch_no=f"B-002-{i+1:03d}",
            factory_id=default_factory_id,
            sampled_at=now - timedelta(days=25 - i),
            subgroup_size=5,
        )
        db.add(b)
        batches_002.append(b)
    await db.flush()

    for i, b in enumerate(batches_002):
        for j in range(5):
            val = round(Decimal(str(245 + rng.gauss(0, 2.5))), 4)
            db.add(SampleValue(
                batch_id=b.batch_id, factory_id=default_factory_id,
                sequence_no=j + 1, value=val, alarm_flags=[],
            ))
    await db.flush()

    db.add(ControlLimitSnapshot(
        ic_id=chars[1].ic_id, factory_id=default_factory_id,
        ucl=Decimal("251.5"), lcl=Decimal("238.5"), cl=Decimal("245.0"),
        r_ucl=Decimal("12.0"), r_lcl=Decimal("0"), r_cl=Decimal("5.8"),
        is_locked=True, version_no=1, is_active=True,
    ))

    # ── Sample Batches & Values for SPC-003 ──
    batches_003 = []
    for i in range(20):
        b = SampleBatch(
            ic_id=chars[2].ic_id, batch_no=f"B-003-{i+1:03d}",
            factory_id=default_factory_id,
            sampled_at=now - timedelta(days=20 - i),
            subgroup_size=5,
        )
        db.add(b)
        batches_003.append(b)
    await db.flush()

    for i, b in enumerate(batches_003):
        for j in range(5):
            val = round(Decimal(str(12.0 + rng.gauss(0, 0.15))), 4)
            db.add(SampleValue(
                batch_id=b.batch_id, factory_id=default_factory_id,
                sequence_no=j + 1, value=val, alarm_flags=[],
            ))
    await db.flush()

    db.add(ControlLimitSnapshot(
        ic_id=chars[2].ic_id, factory_id=default_factory_id,
        ucl=Decimal("12.39"), lcl=Decimal("11.61"), cl=Decimal("12.0"),
        r_ucl=Decimal("0.58"), r_lcl=Decimal("0"), r_cl=Decimal("0.28"),
        is_locked=False, version_no=1, is_active=True,
    ))

    # ── P chart data for SPC-004 (attribute) ──
    batches_004 = []
    for i in range(20):
        b = SampleBatch(
            ic_id=chars[3].ic_id, batch_no=f"B-004-{i+1:03d}",
            factory_id=default_factory_id,
            sampled_at=now - timedelta(days=20 - i),
            subgroup_size=50, inspected_count=50,
            defect_count=max(0, int(rng.gauss(1.5, 1.2))),
        )
        db.add(b)
        batches_004.append(b)
    await db.flush()

    db.add(ControlLimitSnapshot(
        ic_id=chars[3].ic_id, factory_id=default_factory_id,
        ucl=Decimal("6.0"), lcl=Decimal("0"), cl=Decimal("3.0"),
        is_locked=False, version_no=1, is_active=True,
    ))

    await db.flush()
    print("Seeded SPC data.")
    return chars


async def seed_msa(db, admin_id, default_factory_id, gauges, spc_chars):
    """Seed MSA studies: GRR, Bias, Linearity, Stability."""
    # ── GRR Study ──
    from app.models.grr import GrrStudy, GrrMeasurement, GrrResult
    from app.models.bias import BiasStudy, BiasMeasurement, BiasResult
    from app.models.linearity import LinearityStudy, LinearityMeasurement, LinearityResult
    from app.models.stability import StabilityStudy, StabilityMeasurement, StabilityResult

    rng = Random(42)

    # GRR
    existing = await db.execute(select(GrrStudy).where(GrrStudy.study_no == "MSA-GRR-001"))
    if existing.scalar_one_or_none():
        print("MSA data already seeded, skipping.")
        return

    grr_study = GrrStudy(
        study_no="MSA-GRR-001", title="千分尺GRR研究 - 元器件贴装偏移度",
        method="average_range", gauge_id=gauges[0].gauge_id,
        characteristic_name="元器件贴装偏移度", unit="mm",
        tolerance_upper=0.05, tolerance_lower=0.0, reference_value=0.025,
        appraiser_count=3, part_count=10, trial_count=3,
        status="completed", study_date=date(2026, 5, 20),
        product_line_code="DC-DC-100", factory_id=default_factory_id,
        created_by=admin_id,
    )
    db.add(grr_study)
    await db.flush()

    # GRR measurements (3 appraisers × 10 parts × 3 trials)
    appraisers = ["张工", "李工", "王工"]
    for ai, appraiser in enumerate(appraisers):
        for p in range(1, 11):
            for t in range(1, 4):
                base = 0.025 + (p - 5) * 0.003
                val = round(base + ai * 0.001 + rng.gauss(0, 0.002), 4)
                db.add(GrrMeasurement(
                    study_id=grr_study.study_id, factory_id=default_factory_id,
                    appraiser_name=appraiser, part_no=f"P{p:02d}",
                    trial_no=t, value=val,
                ))
    await db.flush()

    # GRR results
    db.add(GrrResult(
        study_id=grr_study.study_id, factory_id=default_factory_id,
        ev=0.0032, av=0.0018, grr=0.0037,
        pv=0.0085, tv=0.0093, ndc=2.3,
        grr_percent_tol=7.4, grr_percent_tv=39.8,
        ev_percent=34.4, av_percent=19.4, pv_percent=91.4,
        conclusion="conditional",
    ))
    await db.flush()

    # ── Bias Study ──
    bias_study = BiasStudy(
        study_no="MSA-BIAS-001", title="千分尺偏倚分析 - 参考值25.000mm",
        gauge_id=gauges[0].gauge_id,
        characteristic_name="测量偏倚", unit="mm",
        reference_value=25.0, sample_size=10,
        status="completed", study_date=date(2026, 5, 22),
        product_line_code="DC-DC-100", factory_id=default_factory_id,
        created_by=admin_id,
    )
    db.add(bias_study)
    await db.flush()

    for i in range(10):
        db.add(BiasMeasurement(
            study_id=bias_study.study_id, factory_id=default_factory_id,
            value=round(25.001 + rng.gauss(0, 0.0005), 4), sequence_no=i + 1,
        ))
    await db.flush()

    db.add(BiasResult(
        study_id=bias_study.study_id, factory_id=default_factory_id,
        mean=25.0012, bias=0.0012, bias_percent=0.0048,
        std_dev=0.0004, t_statistic=9.49, p_value=0.0,
        lower_ci=0.0008, upper_ci=0.0016,
        conclusion="significant",
    ))
    await db.flush()

    # ── Linearity Study ──
    lin_study = LinearityStudy(
        study_no="MSA-LIN-001", title="千分尺线性研究 - 5个参考点",
        gauge_id=gauges[0].gauge_id,
        characteristic_name="测量线性", unit="mm",
        tolerance_upper=0.05, tolerance_lower=0.0,
        sample_size_per_reference=5,
        status="completed", study_date=date(2026, 5, 23),
        product_line_code="DC-DC-100", factory_id=default_factory_id,
        created_by=admin_id,
    )
    db.add(lin_study)
    await db.flush()

    ref_values = [5.0, 10.0, 15.0, 20.0, 25.0]
    for rv in ref_values:
        for seq in range(1, 6):
            db.add(LinearityMeasurement(
                study_id=lin_study.study_id, factory_id=default_factory_id,
                reference_value=rv, measured_value=round(rv + rng.gauss(0, 0.002), 4),
                sequence_no=seq,
            ))
    await db.flush()

    db.add(LinearityResult(
        study_id=lin_study.study_id, factory_id=default_factory_id,
        slope=0.0002, intercept=0.0008, r_squared=0.9998,
        linearity=0.0058, linearity_percent=11.6,
        bias_at_lower=-0.0002, bias_at_upper=0.0058,
        conclusion="conditional",
    ))
    await db.flush()

    # ── Stability Study ──
    stab_study = StabilityStudy(
        study_no="MSA-STAB-001", title="千分尺稳定性研究 - 20天监测",
        gauge_id=gauges[0].gauge_id,
        characteristic_name="测量稳定性", unit="mm",
        reference_value=25.0, subgroup_size=5,
        status="completed", study_date=date(2026, 5, 24),
        product_line_code="DC-DC-100", factory_id=default_factory_id,
        created_by=admin_id,
    )
    db.add(stab_study)
    await db.flush()

    for i in range(20):
        m_date = date(2026, 4, 1) + timedelta(days=i)
        s_mean = round(25.001 + rng.gauss(0, 0.001), 4)
        s_range = round(abs(rng.gauss(0, 0.002)), 4)
        db.add(StabilityMeasurement(
            study_id=stab_study.study_id, factory_id=default_factory_id,
            measurement_date=m_date, sample_mean=s_mean, sample_range=s_range,
            sequence_no=i + 1,
        ))
    await db.flush()

    db.add(StabilityResult(
        study_id=stab_study.study_id, factory_id=default_factory_id,
        ucl_mean=25.004, lcl_mean=24.998, cl_mean=25.001,
        ucl_range=0.006, lcl_range=0.0, cl_range=0.002,
        cpk=1.85, conclusion="acceptable",
    ))
    await db.flush()
    print("Seeded MSA data (GRR, Bias, Linearity, Stability).")


async def seed_iqc_inspections(db, admin_id, default_factory_id, supplier1_id, iqc_materials, capa1_id=None):
    """Seed IQC inspection templates, inspections, items, and measurements."""
    from app.models.iqc_inspection_template import IqcInspectionTemplate, IqcTemplateItem
    from app.models.iqc_inspection import IqcInspection
    from app.models.iqc_inspection_item import IqcInspectionItem, IqcItemMeasurement

    existing = await db.execute(select(IqcInspectionTemplate).where(IqcInspectionTemplate.template_name == "0805贴片电阻进料检验模板"))
    if existing.scalar_one_or_none():
        return

    # ── Templates ──
    mat_res = iqc_materials  # list of IqcMaterial objects

    # Template for resistors
    tmpl1 = IqcInspectionTemplate(
        template_name="0805贴片电阻进料检验模板", material_id=mat_res[0].material_id,
        version=1, is_active=True, factory_id=default_factory_id, created_by=admin_id,
    )
    db.add(tmpl1)
    await db.flush()

    # Template items for resistors
    items1 = [
        IqcTemplateItem(template_id=tmpl1.template_id, factory_id=default_factory_id,
                        sort_order=1, category="外观", item_name="标识清晰度",
                        inspection_method="目视检查", inspect_type="attribute",
                        spec_upper=None, spec_lower=None, target_value=None,
                        unit=None, sample_size=8, aql_level=0.65),
        IqcTemplateItem(template_id=tmpl1.template_id, factory_id=default_factory_id,
                        sort_order=2, category="外观", item_name="焊端氧化",
                        inspection_method="目视检查", inspect_type="attribute",
                        spec_upper=None, spec_lower=None, target_value=None,
                        unit=None, sample_size=8, aql_level=1.0),
        IqcTemplateItem(template_id=tmpl1.template_id, factory_id=default_factory_id,
                        sort_order=3, category="尺寸", item_name="阻值偏差",
                        inspection_method="LCR电桥测量", inspect_type="variable",
                        spec_upper=10200.0, spec_lower=9800.0, target_value=10000.0,
                        unit="Ω", sample_size=5, aql_level=0.4),
    ]
    db.add_all(items1)
    await db.flush()

    # Template for capacitors
    tmpl2 = IqcInspectionTemplate(
        template_name="0805贴片电容进料检验模板", material_id=mat_res[1].material_id,
        version=1, is_active=True, factory_id=default_factory_id, created_by=admin_id,
    )
    db.add(tmpl2)
    await db.flush()

    items2 = [
        IqcTemplateItem(template_id=tmpl2.template_id, factory_id=default_factory_id,
                        sort_order=1, category="外观", item_name="表面缺陷",
                        inspection_method="目视检查", inspect_type="attribute",
                        spec_upper=None, spec_lower=None, target_value=None,
                        unit=None, sample_size=8, aql_level=1.0),
        IqcTemplateItem(template_id=tmpl2.template_id, factory_id=default_factory_id,
                        sort_order=2, category="电气", item_name="电容量",
                        inspection_method="LCR电桥测量", inspect_type="variable",
                        spec_upper=12.0, spec_lower=8.0, target_value=10.0,
                        unit="μF", sample_size=5, aql_level=0.65),
    ]
    db.add_all(items2)
    await db.flush()

    # Template for PCB
    tmpl3 = IqcInspectionTemplate(
        template_name="DC-DC PCB板进料检验模板", material_id=mat_res[2].material_id,
        version=1, is_active=True, factory_id=default_factory_id, created_by=admin_id,
    )
    db.add(tmpl3)
    await db.flush()

    items3 = [
        IqcTemplateItem(template_id=tmpl3.template_id, factory_id=default_factory_id,
                        sort_order=1, category="外观", item_name="板面划伤",
                        inspection_method="目视检查", inspect_type="attribute",
                        spec_upper=None, spec_lower=None, target_value=None,
                        unit=None, sample_size=3, aql_level=0.4),
        IqcTemplateItem(template_id=tmpl3.template_id, factory_id=default_factory_id,
                        sort_order=2, category="尺寸", item_name="板厚",
                        inspection_method="千分尺测量", inspect_type="variable",
                        spec_upper=1.7, spec_lower=1.5, target_value=1.6,
                        unit="mm", sample_size=5, aql_level=0.4),
    ]
    db.add_all(items3)
    await db.flush()

    # ── Inspections ──
    # Inspection 1: ACCEPTED
    insp1 = IqcInspection(
        inspection_no="IQC-2026-001", supplier_id=supplier1_id,
        part_no="RES-0805-10K", part_name="0805贴片电阻 10KΩ ±1%",
        lot_no="LOT-2026-0501", lot_qty=5000, sample_qty=8,
        aql_level="0.65", inspection_level="II",
        inspection_result="accepted", defect_qty=0,
        status="completed", inspection_mode="full",
        material_id=mat_res[0].material_id, template_id=tmpl1.template_id,
        code_letter="D", accept_number=0, reject_number=1,
        inspected_by=admin_id, judged_by=admin_id,
        judged_at=datetime(2026, 5, 20, 14, 30, tzinfo=UTC),
        inspection_date=date(2026, 5, 20),
        product_line_code="DC-DC-100", factory_id=default_factory_id,
    )
    db.add(insp1)
    await db.flush()

    # Items for inspection 1
    insp1_items = [
        IqcInspectionItem(
            inspection_id=insp1.inspection_id, factory_id=default_factory_id,
            template_item_id=items1[0].item_id, sort_order=1,
            category="外观", item_name="标识清晰度", inspect_type="attribute",
            sample_size=8, accept_no=0, reject_no=1, defect_qty=0,
            result="accepted", remark="全部合格",
        ),
        IqcInspectionItem(
            inspection_id=insp1.inspection_id, factory_id=default_factory_id,
            template_item_id=items1[1].item_id, sort_order=2,
            category="外观", item_name="焊端氧化", inspect_type="attribute",
            sample_size=8, accept_no=0, reject_no=1, defect_qty=0,
            result="accepted", remark="无氧化",
        ),
        IqcInspectionItem(
            inspection_id=insp1.inspection_id, factory_id=default_factory_id,
            template_item_id=items1[2].item_id, sort_order=3,
            category="尺寸", item_name="阻值偏差", inspect_type="variable",
            spec_upper=10200.0, spec_lower=9800.0, target_value=10000.0,
            sample_size=5, accept_no=0, reject_no=1, defect_qty=0,
            result="accepted",
        ),
    ]
    db.add_all(insp1_items)
    await db.flush()

    # Measurements for the variable item (阻值偏差)
    for seq, val in enumerate([9985, 10012, 9973, 10008, 9942], 1):
        db.add(IqcItemMeasurement(
            item_id=insp1_items[2].item_id, factory_id=default_factory_id,
            sequence_no=seq, measured_value=float(val), attribute_result=None,
        ))
    await db.flush()

    # Inspection 2: REJECTED
    insp2 = IqcInspection(
        inspection_no="IQC-2026-002", supplier_id=supplier1_id,
        part_no="CAP-0805-10U", part_name="0805贴片电容 10uF ±20%",
        lot_no="LOT-2026-0505", lot_qty=3000, sample_qty=8,
        aql_level="1.0", inspection_level="II",
        inspection_result="rejected", defect_qty=3, defect_description="3件电容量超出上限",
        status="completed", inspection_mode="full",
        material_id=mat_res[1].material_id, template_id=tmpl2.template_id,
        code_letter="D", accept_number=0, reject_number=1,
        inspected_by=admin_id, judged_by=admin_id,
        judged_at=datetime(2026, 5, 25, 16, 0, tzinfo=UTC),
        inspection_date=date(2026, 5, 25),
        product_line_code="DC-DC-100", factory_id=default_factory_id,
        has_safety_defect=False,
    )
    db.add(insp2)
    await db.flush()

    insp2_items = [
        IqcInspectionItem(
            inspection_id=insp2.inspection_id, factory_id=default_factory_id,
            template_item_id=items2[0].item_id, sort_order=1,
            category="外观", item_name="表面缺陷", inspect_type="attribute",
            sample_size=8, accept_no=0, reject_no=1, defect_qty=0,
            result="accepted",
        ),
        IqcInspectionItem(
            inspection_id=insp2.inspection_id, factory_id=default_factory_id,
            template_item_id=items2[1].item_id, sort_order=2,
            category="电气", item_name="电容量", inspect_type="variable",
            spec_upper=12.0, spec_lower=8.0, target_value=10.0,
            sample_size=5, accept_no=0, reject_no=1, defect_qty=3,
            result="rejected", remark="3件超上限",
        ),
    ]
    db.add_all(insp2_items)
    await db.flush()

    for seq, val in enumerate([10.2, 12.5, 9.8, 12.8, 11.1], 1):
        db.add(IqcItemMeasurement(
            item_id=insp2_items[1].item_id, factory_id=default_factory_id,
            sequence_no=seq, measured_value=val, attribute_result=None,
        ))
    await db.flush()

    # Inspection 3: PENDING
    insp3 = IqcInspection(
        inspection_no="IQC-2026-003", supplier_id=supplier1_id,
        part_no="PCB-DC-001", part_name="DC-DC电源模块PCB板",
        lot_no="LOT-2026-0528", lot_qty=1000, sample_qty=5,
        aql_level="0.4", inspection_level="II",
        inspection_result="pending", defect_qty=0,
        status="pending", inspection_mode="full",
        material_id=mat_res[2].material_id, template_id=tmpl3.template_id,
        code_letter="C", accept_number=0, reject_number=1,
        inspection_date=date(2026, 6, 1),
        product_line_code="DC-DC-100", factory_id=default_factory_id,
    )
    db.add(insp3)
    await db.flush()
    print("Seeded IQC inspections, templates, and items.")


async def seed_control_plans(db, admin_id, manager_id, default_factory_id, fmea1_id):
    """Seed control plans with items."""
    from app.models.control_plan import ControlPlan, ControlPlanItem

    existing = await db.execute(select(ControlPlan).where(ControlPlan.document_no == "CP-2026-001"))
    if existing.scalar_one_or_none():
        return

    cp = ControlPlan(
        document_no="CP-2026-001", title="DC-DC 100W 电源模块控制计划",
        fmea_ref_id=fmea1_id, product_line_code="DC-DC-100",
        factory_id=default_factory_id, status="approved", version=1,
        phase="production", part_no="DCDC-100W-A", part_name="DC-DC 100W电源模块",
        contact_info="质量部 张工", drawing_rev="Rev.C",
        org_factory="DEFAULT", core_group="张工,李工,王工",
        created_by=admin_id, updated_by=admin_id, approved_by=manager_id,
        approved_at=datetime(2026, 5, 1, 10, 0, tzinfo=UTC),
    )
    db.add(cp)
    await db.flush()

    # Control plan items linked to FMEA nodes
    cp_items = [
        ControlPlanItem(
            cp_id=cp.cp_id, factory_id=default_factory_id, sort_order=1,
            step_no="10", process_name="SMT贴装",
            equipment="高速贴片机",
            characteristic_no="SC-001", product_characteristic="元器件贴装偏移度",
            process_characteristic="贴装压力", special_class="CC",
            specification_tolerance="≤0.05mm / 3.0±0.5N",
            evaluation_method="3D-AOI检测", sample_size="5件/批",
            sample_frequency="每批次", control_method="SPC Xbar-R图",
            reaction_plan="调整贴装参数, 联系设备工程师",
            source_fmea_node_id="psf_1", item_source="fmea",
        ),
        ControlPlanItem(
            cp_id=cp.cp_id, factory_id=default_factory_id, sort_order=2,
            step_no="20", process_name="回流焊接",
            equipment="回流焊炉",
            characteristic_no="SC-002", product_characteristic="焊接质量",
            process_characteristic="炉温曲线", special_class="SC",
            specification_tolerance="峰值温度235-255℃",
            evaluation_method="炉温测试仪", sample_size="1次/班",
            sample_frequency="每班", control_method="温度曲线监控",
            reaction_plan="调整炉温参数, 通知工艺工程师",
            source_fmea_node_id="wef_1", item_source="fmea",
        ),
        ControlPlanItem(
            cp_id=cp.cp_id, factory_id=default_factory_id, sort_order=3,
            step_no="30", process_name="功能测试",
            equipment="综合测试台",
            characteristic_no="CC-001", product_characteristic="空载转速",
            process_characteristic="测试参数设置", special_class="CC",
            specification_tolerance="3500±50 RPM",
            evaluation_method="全检", sample_size="100%",
            sample_frequency="每件", control_method="全检记录",
            reaction_plan="隔离不合格品, 启动8D",
            source_fmea_node_id="fm-cc-001", item_source="fmea",
        ),
        ControlPlanItem(
            cp_id=cp.cp_id, factory_id=default_factory_id, sort_order=4,
            step_no="40", process_name="终检包装",
            equipment="目视检验台",
            characteristic_no="", product_characteristic="外观质量",
            process_characteristic="包装防护", special_class="",
            specification_tolerance="无划伤/无损伤",
            evaluation_method="目视检查", sample_size="AQL 1.0",
            sample_frequency="每批", control_method="抽检记录",
            reaction_plan="更换包装材料, 返工",
            item_source="manual",
        ),
    ]
    db.add_all(cp_items)
    await db.flush()
    print("Seeded control plans.")


async def seed_audits(db, admin_id, engineer_id, manager_id, default_factory_id, capa1_id=None):
    """Seed audit programs, plans, and findings."""
    from app.models.audit_program import AuditProgram, AuditProgramTargetFactory
    from app.models.audit_plan import AuditPlan
    from app.models.audit_finding import AuditFinding

    existing = await db.execute(select(AuditProgram).where(AuditProgram.program_no == "AP-2026-001"))
    if existing.scalar_one_or_none():
        return

    # ── Audit Program 1: Internal quality system audit ──
    prog1 = AuditProgram(
        program_no="AP-2026-001", program_year=2026,
        audit_type="internal", scope="IATF 16949质量管理体系内部审核",
        criteria="IATF 16949:2016, 公司质量手册V3.2",
        status="in_progress", created_by=admin_id,
        product_line_code="DC-DC-100", factory_id=default_factory_id,
    )
    db.add(prog1)
    await db.flush()

    db.add(AuditProgramTargetFactory(
        program_id=prog1.program_id, factory_id=default_factory_id,
    ))
    await db.flush()

    # ── Audit Program 2: Process audit ──
    prog2 = AuditProgram(
        program_no="AP-2026-002", program_year=2026,
        audit_type="process", scope="SMT焊接过程审核",
        criteria="VDA 6.3过程审核标准",
        status="planned", created_by=admin_id,
        product_line_code="DC-DC-100", factory_id=default_factory_id,
    )
    db.add(prog2)
    await db.flush()

    db.add(AuditProgramTargetFactory(
        program_id=prog2.program_id, factory_id=default_factory_id,
    ))
    await db.flush()

    # ── Audit Plan 1 ──
    plan1 = AuditPlan(
        plan_no="AUD-2026-001", program_id=prog1.program_id,
        audit_scope="质量管理体系全要素审核",
        audit_criteria="IATF 16949条款8.3-8.7",
        planned_date=date(2026, 6, 15),
        actual_date=date(2026, 6, 16),
        lead_auditor=manager_id,
        team_members=[
            {"user_id": str(engineer_id), "name": "质量工程师", "role": "审核员"},
            {"user_id": str(admin_id), "name": "系统管理员", "role": "审核员"},
        ],
        checklist=[
            {"clause": "8.3.2", "question": "是否制定了设计和开发计划?", "result": "符合"},
            {"clause": "8.3.3", "question": "设计输入是否充分?", "result": "符合"},
            {"clause": "8.3.4", "question": "设计评审是否按计划执行?", "result": "不符合"},
            {"clause": "8.4.2", "question": "供应商是否经过批准?", "result": "符合"},
            {"clause": "8.5.1", "question": "生产是否在受控条件下进行?", "result": "符合"},
        ],
        status="completed",
        created_by=admin_id,
        product_line_code="DC-DC-100",
        audit_category="internal",
    )
    db.add(plan1)
    await db.flush()

    # ── Audit Finding 1: Major NC ──
    finding1 = AuditFinding(
        audit_id=plan1.audit_id, factory_id=default_factory_id,
        clause_ref="8.3.4", finding_type="major",
        description="设计评审未按计划执行，PFMEA变更后未重新评审",
        root_cause="项目进度紧张，评审计划未被严格执行",
        correction="立即补做设计评审，并更新评审记录",
        corrective_action="修订设计评审流程，增加评审提醒和审批机制",
        capa_ref_id=capa1_id,
        status="in_progress", due_date=date(2026, 7, 15),
        created_by=admin_id,
    )
    db.add(finding1)

    # ── Audit Finding 2: Minor NC ──
    finding2 = AuditFinding(
        audit_id=plan1.audit_id, factory_id=default_factory_id,
        clause_ref="8.5.1", finding_type="minor",
        description="SMT产线作业指导书版本未及时更新",
        root_cause="文件管理流程执行偏差",
        correction="更新作业指导书至最新版本",
        corrective_action="建立文件版本自动提醒机制",
        status="open", due_date=date(2026, 7, 30),
        created_by=admin_id,
    )
    db.add(finding2)

    # ── Audit Finding 3: Observation ──
    finding3 = AuditFinding(
        audit_id=plan1.audit_id, factory_id=default_factory_id,
        clause_ref="8.4.2", finding_type="observation",
        description="建议增加供应商现场审核频次，特别是C级供应商",
        status="open", due_date=date(2026, 8, 31),
        created_by=admin_id,
    )
    db.add(finding3)
    await db.flush()

    # ── Audit Plan 2: planned ──
    plan2 = AuditPlan(
        plan_no="AUD-2026-002", program_id=prog2.program_id,
        audit_scope="SMT焊接过程审核",
        audit_criteria="VDA 6.3过程审核标准",
        planned_date=date(2026, 7, 20),
        lead_auditor=manager_id,
        team_members=[
            {"user_id": str(engineer_id), "name": "质量工程师", "role": "审核员"},
        ],
        checklist=[],
        status="planned",
        created_by=admin_id,
        product_line_code="DC-DC-100",
        audit_category="process",
    )
    db.add(plan2)
    await db.flush()

    # ── Audit Program 3: Customer audit ──
    prog3 = AuditProgram(
        program_no="AP-2026-003", program_year=2026,
        audit_type="customer", scope="上海新能源主机厂第二方审核",
        criteria="客户CSR要求",
        status="completed", created_by=admin_id,
        product_line_code="DC-DC-100", factory_id=default_factory_id,
    )
    db.add(prog3)
    await db.flush()

    db.add(AuditProgramTargetFactory(
        program_id=prog3.program_id, factory_id=default_factory_id,
    ))

    plan3 = AuditPlan(
        plan_no="AUD-2026-003", program_id=prog3.program_id,
        audit_scope="客户第二方审核",
        audit_criteria="上海新能源CSR + IATF 16949",
        planned_date=date(2026, 4, 10),
        actual_date=date(2026, 4, 11),
        lead_auditor=manager_id,
        team_members=[],
        checklist=[
            {"clause": "CSR-01", "question": "24小时响应机制是否建立?", "result": "符合"},
            {"clause": "CSR-02", "question": "批次追溯体系是否完善?", "result": "基本符合"},
        ],
        status="completed",
        created_by=admin_id,
        product_line_code="DC-DC-100",
        audit_category="customer", customer_name="上海新能源主机厂",
        customer_type="automotive",
        customer_confirmation_doc=[],
    )
    db.add(plan3)
    await db.flush()

    finding4 = AuditFinding(
        audit_id=plan3.audit_id, factory_id=default_factory_id,
        clause_ref="CSR-02", finding_type="minor",
        description="批次追溯系统未覆盖原材料批次信息",
        root_cause="系统未集成原材料批次追溯模块",
        correction="补充原材料批次追溯信息",
        status="closed", due_date=date(2026, 5, 30),
        closed_at=datetime(2026, 5, 28, 10, 0, tzinfo=UTC),
        customer_confirmed=True, customer_confirmation_date=date(2026, 5, 29),
        created_by=admin_id,
    )
    db.add(finding4)
    await db.flush()
    print("Seeded audit programs, plans, and findings.")


async def seed_ppap(db, admin_id, manager_id, default_factory_id, supplier1_id, supplier2_id):
    """Seed PPAP submissions."""
    from app.models.supplier import SupplierPPAPSubmission, SupplierPPAPElement

    existing = await db.execute(select(SupplierPPAPSubmission).where(SupplierPPAPSubmission.ppap_no == "PPAP-2026-001"))
    if existing.scalar_one_or_none():
        return

    # PPAP Submission 1: Level 3 (full)
    ppap1 = SupplierPPAPSubmission(
        ppap_no="PPAP-2026-001",
        supplier_id=supplier1_id, factory_id=default_factory_id,
        part_no="RES-0805-10K", part_name="0805贴片电阻 10KΩ",
        submission_level=3, submission_date=date(2026, 3, 15),
        status="approved", approved_by=manager_id,
        approved_at=datetime(2026, 3, 25, 10, 0, tzinfo=UTC),
        notes="Level 3全项提交，所有项目符合要求",
        product_line_code="DC-DC-100",
        customer_name="上海新能源主机厂",
        created_by=admin_id,
    )
    db.add(ppap1)
    await db.flush()

    # PPAP elements (18 standard elements)
    ppap_elements_1 = [
        SupplierPPAPElement(submission_id=ppap1.submission_id, element_no=1, element_name="设计记录", status="approved", sort_order=1, required=True, reviewed_by=manager_id),
        SupplierPPAPElement(submission_id=ppap1.submission_id, element_no=2, element_name="工程变更文件", status="approved", sort_order=2, required=True, reviewed_by=manager_id),
        SupplierPPAPElement(submission_id=ppap1.submission_id, element_no=3, element_name="顾客工程批准", status="approved", sort_order=3, required=False, reviewed_by=manager_id),
        SupplierPPAPElement(submission_id=ppap1.submission_id, element_no=4, element_name="设计FMEA", status="approved", sort_order=4, required=True, reviewed_by=manager_id),
        SupplierPPAPElement(submission_id=ppap1.submission_id, element_no=5, element_name="过程流程图", status="approved", sort_order=5, required=True, reviewed_by=manager_id),
        SupplierPPAPElement(submission_id=ppap1.submission_id, element_no=6, element_name="过程FMEA", status="approved", sort_order=6, required=True, reviewed_by=manager_id),
        SupplierPPAPElement(submission_id=ppap1.submission_id, element_no=7, element_name="控制计划", status="approved", sort_order=7, required=True, reviewed_by=manager_id),
        SupplierPPAPElement(submission_id=ppap1.submission_id, element_no=8, element_name="测量系统分析", status="approved", sort_order=8, required=True, reviewed_by=manager_id),
        SupplierPPAPElement(submission_id=ppap1.submission_id, element_no=9, element_name="尺寸结果", status="approved", sort_order=9, required=True, reviewed_by=manager_id),
        SupplierPPAPElement(submission_id=ppap1.submission_id, element_no=10, element_name="材料/性能试验结果", status="approved", sort_order=10, required=True, reviewed_by=manager_id),
        SupplierPPAPElement(submission_id=ppap1.submission_id, element_no=11, element_name="初始过程研究", status="approved", sort_order=11, required=True, reviewed_by=manager_id),
        SupplierPPAPElement(submission_id=ppap1.submission_id, element_no=12, element_name="合格实验室文件", status="approved", sort_order=12, required=True, reviewed_by=manager_id),
        SupplierPPAPElement(submission_id=ppap1.submission_id, element_no=13, element_name="外观批准报告", status="na", sort_order=13, required=False),
        SupplierPPAPElement(submission_id=ppap1.submission_id, element_no=14, element_name="样品产品", status="approved", sort_order=14, required=True, reviewed_by=manager_id),
        SupplierPPAPElement(submission_id=ppap1.submission_id, element_no=15, element_name="检查辅具", status="approved", sort_order=15, required=True, reviewed_by=manager_id),
        SupplierPPAPElement(submission_id=ppap1.submission_id, element_no=16, element_name="顾客特殊要求", status="approved", sort_order=16, required=True, reviewed_by=manager_id),
        SupplierPPAPElement(submission_id=ppap1.submission_id, element_no=17, element_name="零件提交保证书", status="approved", sort_order=17, required=True, reviewed_by=manager_id),
        SupplierPPAPElement(submission_id=ppap1.submission_id, element_no=18, element_name="零件重量记录", status="approved", sort_order=18, required=True, reviewed_by=manager_id),
    ]
    db.add_all(ppap_elements_1)

    # PPAP Submission 2: Level 1 (pending)
    ppap2 = SupplierPPAPSubmission(
        ppap_no="PPAP-2026-002",
        supplier_id=supplier2_id, factory_id=default_factory_id,
        part_no="PCB-DC-001", part_name="DC-DC电源模块PCB板",
        submission_level=1, submission_date=date(2026, 5, 28),
        status="pending",
        notes="Level 1提交，等待审核",
        product_line_code="DC-DC-100",
        created_by=admin_id,
    )
    db.add(ppap2)
    await db.flush()

    ppap_elements_2 = [
        SupplierPPAPElement(submission_id=ppap2.submission_id, element_no=1, element_name="设计记录", status="pending", sort_order=1, required=True),
        SupplierPPAPElement(submission_id=ppap2.submission_id, element_no=7, element_name="控制计划", status="pending", sort_order=2, required=True),
        SupplierPPAPElement(submission_id=ppap2.submission_id, element_no=9, element_name="尺寸结果", status="pending", sort_order=3, required=True),
        SupplierPPAPElement(submission_id=ppap2.submission_id, element_no=17, element_name="零件提交保证书", status="pending", sort_order=4, required=True),
    ]
    db.add_all(ppap_elements_2)
    await db.flush()
    print("Seeded PPAP submissions.")


async def seed_quality_goals(db, admin_id, engineer_id, manager_id, default_factory_id):
    """Seed quality goals with hierarchy."""
    from app.models.quality_goal import QualityGoal

    existing = await db.execute(select(QualityGoal).where(QualityGoal.doc_no == "QG-2026-001"))
    if existing.scalar_one_or_none():
        return

    # Top-level goals
    goal1 = QualityGoal(
        doc_no="QG-2026-001", level=1,
        product_line_code="DC-DC-100", factory_id=default_factory_id,
        name="DC-DC-100产品线质量目标", target_value="95%", actual_value="92.3%",
        unit="%", period="yearly", owner_id=manager_id,
        status="approved", approved_by=admin_id,
        approved_at=datetime(2026, 1, 15, 10, 0, tzinfo=UTC),
        description="DC-DC-100产品线2026年度总质量目标",
        data_source_formula="综合达成率",
    )
    db.add(goal1)
    await db.flush()

    # Sub-goals
    sub_goals = [
        QualityGoal(
            doc_no="QG-2026-001-01", parent_id=goal1.goal_id, level=2,
            product_line_code="DC-DC-100", factory_id=default_factory_id,
            name="客诉PPM目标", target_value="≤100ppm", actual_value="85ppm",
            unit="ppm", period="yearly", owner_id=engineer_id,
            status="approved", approved_by=admin_id,
            approved_at=datetime(2026, 1, 15, 10, 30, tzinfo=UTC),
            description="客户投诉PPM控制目标",
        ),
        QualityGoal(
            doc_no="QG-2026-001-02", parent_id=goal1.goal_id, level=2,
            product_line_code="DC-DC-100", factory_id=default_factory_id,
            name="出货合格率", target_value="≥99.5%", actual_value="99.3%",
            unit="%", period="monthly", owner_id=engineer_id,
            status="approved", approved_by=admin_id,
            approved_at=datetime(2026, 1, 15, 10, 30, tzinfo=UTC),
            description="出货批次合格率目标",
        ),
        QualityGoal(
            doc_no="QG-2026-001-03", parent_id=goal1.goal_id, level=2,
            product_line_code="DC-DC-100", factory_id=default_factory_id,
            name="SPC Cpk达标率", target_value="≥1.33", actual_value="1.25",
            unit="Cpk", period="quarterly", owner_id=engineer_id,
            status="in_progress",
            description="关键特性Cpk达标比例",
        ),
        QualityGoal(
            doc_no="QG-2026-001-04", parent_id=goal1.goal_id, level=2,
            product_line_code="DC-DC-100", factory_id=default_factory_id,
            name="供应商来料合格率", target_value="≥98%", actual_value="96.5%",
            unit="%", period="monthly", owner_id=engineer_id,
            status="draft",
            description="供应商来料批次合格率",
        ),
    ]
    db.add_all(sub_goals)
    await db.flush()

    # 3rd level goal
    db.add(QualityGoal(
        doc_no="QG-2026-001-01-01", parent_id=sub_goals[0].goal_id, level=3,
        product_line_code="DC-DC-100", factory_id=default_factory_id,
        name="安全相关客诉PPM", target_value="≤0ppm", actual_value="0ppm",
        unit="ppm", period="yearly", owner_id=engineer_id,
        status="approved", approved_by=admin_id,
        approved_at=datetime(2026, 1, 15, 11, 0, tzinfo=UTC),
        description="安全相关客户投诉PPM（零容忍）",
    ))
    await db.flush()
    print("Seeded quality goals.")


async def seed_scars(db, admin_id, engineer_id, default_factory_id, supplier1_id, supplier2_id, capa1_id=None):
    """Seed Supplier Corrective Action Requests."""
    from app.models.supplier import SupplierSCAR

    existing = await db.execute(select(SupplierSCAR).where(SupplierSCAR.scar_no == "SCAR-2026-001"))
    if existing.scalar_one_or_none():
        return

    scar1 = SupplierSCAR(
        scar_no="SCAR-2026-001",
        supplier_id=supplier1_id, factory_id=default_factory_id,
        source_type="incoming_inspection",
        description="IQC检验发现0805贴片电容电容量超差，3/8样品超出上限",
        product_line_code="DC-DC-100",
        requested_action="请在10个工作日内提交8D报告及改善对策",
        supplier_response="已启动内部改善，预计2周内提交8D报告",
        status="in_progress",
        issued_by=engineer_id, issued_date=date(2026, 5, 26),
        due_date=date(2026, 6, 9),
        capa_ref_id=capa1_id,
    )
    db.add(scar1)

    scar2 = SupplierSCAR(
        scar_no="SCAR-2026-002",
        supplier_id=supplier2_id, factory_id=default_factory_id,
        source_type="complaint",
        description="客户投诉包装材料划伤，追溯到供应商包装工艺不足",
        product_line_code="DC-DC-100",
        requested_action="请改善包装工艺，增加防护措施",
        supplier_response="已完成包装材料升级，增加泡沫隔板",
        status="closed",
        issued_by=engineer_id, issued_date=date(2026, 4, 15),
        due_date=date(2026, 5, 15),
        closed_date=date(2026, 5, 10),
        resolution_summary="供应商已更换包装材料并增加防护措施，验证合格后关闭",
    )
    db.add(scar2)
    await db.flush()
    print("Seeded SCAR records.")


async def seed_mes_mock(db, admin_id, default_factory_id):
    """Seed MES mock connection, equipment status, production orders, and scrap data."""
    from app.models.mes import (
        MESConnection, MESEquipmentStatus, MESProductionOrder, MESScrapRecord,
    )

    existing = await db.execute(select(MESConnection).where(MESConnection.name == "DC-DC MES (Mock)"))
    if existing.scalar_one_or_none():
        return

    mes_conn = MESConnection(
        name="DC-DC MES (Mock)",
        connector_type="mock",
        config={}, is_active=True,
        product_line_code="DC-DC-100",
        factory_id=default_factory_id,
        created_by=admin_id,
    )
    db.add(mes_conn)
    await db.flush()

    rng = Random(42)
    now = datetime.now(UTC)

    # Equipment status
    equipment_list = [
        ("EQ-001", "SMT贴片机-1", "running", 95.2, 88.5, 99.1, 83.5),
        ("EQ-002", "SMT贴片机-2", "running", 93.8, 86.2, 98.8, 80.1),
        ("EQ-003", "回流焊炉-1", "running", 97.5, 92.1, 99.5, 89.3),
        ("EQ-004", "综合测试台-1", "running", 91.0, 85.0, 99.2, 76.6),
        ("EQ-005", "AOI检测仪-1", "idle", 85.0, 78.0, 99.0, 65.5),
        ("EQ-006", "点胶机-1", "maintenance", 60.0, 45.0, 95.0, 25.7),
    ]
    for eq_code, eq_name, status, avail, perf, qual, oee in equipment_list:
        db.add(MESEquipmentStatus(
            connection_id=mes_conn.connection_id, factory_id=default_factory_id,
            external_id=f"mes-eq-{eq_code}", equipment_code=eq_code,
            equipment_name=eq_name, status=status,
            availability=Decimal(str(avail)), performance=Decimal(str(perf)),
            quality=Decimal(str(qual)), oee=Decimal(str(oee)),
            downtime_reason="计划性维护" if status == "maintenance" else None,
            recorded_at=now, product_line_code="DC-DC-100",
        ))

    # Production orders
    orders = [
        ("PO-2026-001", "DCDC-100W-A", "SMT→回流焊→测试→包装", 5000, 4850, "completed"),
        ("PO-2026-002", "DCDC-100W-B", "SMT→回流焊→测试→包装", 3000, 2850, "in_progress"),
        ("PO-2026-003", "DCDC-100W-C", "SMT→回流焊→测试→包装", 2000, 0, "planned"),
    ]
    for order_no, model, route, planned, actual, status in orders:
        db.add(MESProductionOrder(
            connection_id=mes_conn.connection_id, factory_id=default_factory_id,
            order_no=order_no, product_model=model, process_route=route,
            planned_qty=planned, actual_qty=actual, status=status,
            started_at=now - timedelta(days=10) if status in ("completed", "in_progress") else None,
            completed_at=now - timedelta(days=2) if status == "completed" else None,
            product_line_code="DC-DC-100",
        ))
    await db.flush()

    # Scrap records
    scrap_types = [
        ("焊接不良", "solder_defect", 12, 5000),
        ("贴装偏移", "placement_error", 8, 5000),
        ("外观划伤", "cosmetic", 5, 4850),
        ("电气不良", "electrical", 3, 4850),
    ]
    for defect, category, qty, total in scrap_types:
        db.add(MESScrapRecord(
            connection_id=mes_conn.connection_id, factory_id=default_factory_id,
            external_id=f"mes-scrap-{defect[:3]}", order_no="PO-2026-001",
            equipment_code="EQ-001", defect_type=defect,
            defect_category=category, defect_qty=qty, total_qty=total,
            recorded_at=now - timedelta(days=rng.randint(1, 14)),
            product_line_code="DC-DC-100",
        ))
    await db.flush()
    print("Seeded MES mock data.")


async def seed_erp_mock(db, admin_id, default_factory_id):
    """Seed ERP mock connection and basic data."""
    from app.models.erp import ERPConnection

    existing = await db.execute(select(ERPConnection).limit(1))
    if existing.scalar_one_or_none():
        return

    erp_conn = ERPConnection(
        name="DC-DC ERP (Mock)",
        connector_type="mock",
        config={}, is_active=True,
        product_line_code="DC-DC-100",
        factory_id=default_factory_id,
        created_by=admin_id,
    )
    db.add(erp_conn)
    await db.flush()
    print("Seeded ERP mock connection.")


async def seed_apqp(db, admin_id, engineer_id, default_factory_id, fmea1_id, fmea3_id=None):
    """Seed APQP projects."""
    from app.models.apqp import APQPProject

    existing = await db.execute(select(APQPProject).where(APQPProject.project_code == "APQP-2026-001"))
    if existing.scalar_one_or_none():
        return

    # APQP Project 1: Active, in Phase 3
    proj1 = APQPProject(
        project_code="APQP-2026-001",
        project_name="DC-DC 100W BMS电源模块新品开发",
        product_name="DC-DC 100W BMS电源模块",
        product_line_code="DC-DC-100", factory_id=default_factory_id,
        customer_name="上海新能源主机厂",
        description="为上海新能源主机厂开发新一代DC-DC 100W BMS电源模块，满足车规级要求",
        target_sop_date=date(2026, 9, 1),
        team_members=[
            {"name": "张工", "role": "项目经理", "department": "研发部"},
            {"name": "李工", "role": "质量工程师", "department": "质量部"},
            {"name": "王工", "role": "工艺工程师", "department": "工艺部"},
            {"name": "赵工", "role": "采购工程师", "department": "采购部"},
        ],
        current_phase=3, phase_status="in_progress", project_status="active",
        phase_1_completed_at=datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
        phase_2_completed_at=datetime(2026, 4, 15, 14, 0, tzinfo=UTC),
        pfmea_id=fmea1_id,
        dfmea_id=fmea3_id,
        created_by=admin_id,
    )
    db.add(proj1)

    # APQP Project 2: Completed
    proj2 = APQPProject(
        project_code="APQP-2025-003",
        project_name="DC-DC 50W 电源模块量产导入",
        product_name="DC-DC 50W 电源模块",
        product_line_code="DC-DC-100", factory_id=default_factory_id,
        customer_name="苏州工业控制有限公司",
        description="DC-DC 50W工业级电源模块量产导入项目，已完成全部APQP阶段",
        target_sop_date=date(2026, 2, 1),
        team_members=[
            {"name": "李工", "role": "质量工程师", "department": "质量部"},
        ],
        current_phase=5, phase_status="completed", project_status="completed",
        phase_1_completed_at=datetime(2025, 9, 1, 10, 0, tzinfo=UTC),
        phase_2_completed_at=datetime(2025, 10, 15, 14, 0, tzinfo=UTC),
        phase_3_completed_at=datetime(2025, 11, 30, 16, 0, tzinfo=UTC),
        phase_4_completed_at=datetime(2026, 1, 15, 10, 0, tzinfo=UTC),
        phase_5_completed_at=datetime(2026, 2, 1, 10, 0, tzinfo=UTC),
        gate_approved_by=admin_id,
        gate_approved_at=datetime(2026, 2, 1, 10, 30, tzinfo=UTC),
        gate_comments="项目各阶段均达标，批准量产",
        gate_history=[
            {"phase": 1, "approved_by": "系统管理员", "approved_at": "2025-09-01T10:00:00Z", "comments": "计划与目标确认完成"},
            {"phase": 2, "approved_by": "系统管理员", "approved_at": "2025-10-15T14:00:00Z", "comments": "产品设计与开发阶段完成"},
            {"phase": 3, "approved_by": "系统管理员", "approved_at": "2025-11-30T16:00:00Z", "comments": "过程设计与开发完成"},
            {"phase": 4, "approved_by": "系统管理员", "approved_at": "2026-01-15T10:00:00Z", "comments": "产品与过程确认完成"},
            {"phase": 5, "approved_by": "系统管理员", "approved_at": "2026-02-01T10:30:00Z", "comments": "反馈与评定完成，批准量产"},
        ],
        created_by=admin_id,
    )
    db.add(proj2)

    # APQP Project 3: Early phase, planning
    proj3 = APQPProject(
        project_code="APQP-2026-004",
        project_name="车载充电机AC-DC模块新品开发",
        product_name="AC-DC 车载充电机模块",
        product_line_code="DC-DC-100", factory_id=default_factory_id,
        description="新能源汽车车载充电机AC-DC模块APQP项目",
        target_sop_date=date(2027, 3, 1),
        team_members=[
            {"name": "张工", "role": "项目经理", "department": "研发部"},
        ],
        current_phase=1, phase_status="in_progress", project_status="active",
        created_by=admin_id,
    )
    db.add(proj3)
    await db.flush()
    print("Seeded APQP projects.")


async def seed():
    async with async_session() as db:
        # ─── Seed roles if missing (single-tenant mode) ───
        from app.models.role import RoleDefinition, RolePermission
        role_result = await db.execute(select(RoleDefinition))
        existing_roles = {r.role_key for r in role_result.scalars().all()}
        _ROLES = [
            ("admin", "系统管理员", "System Admin", True, False, True, 1),
            ("manager", "质量经理", "Quality Manager", True, True, False, 2),
            ("viewer", "只读用户", "Viewer", True, False, False, 3),
            ("customer_qe", "客户质量工程师", "Customer QE", True, True, False, 4),
            ("supplier_qe", "供应商质量工程师", "Supplier QE", True, True, False, 5),
            ("field_qe", "现场质量工程师", "Field QE", True, True, False, 6),
            ("planning_qe", "前期策划质量工程师", "Planning QE", True, True, False, 7),
        ]
        for role_key, name_zh, name_en, is_system, is_editable, bypass, sort in _ROLES:
            if role_key not in existing_roles:
                db.add(RoleDefinition(
                    role_key=role_key,
                    name_zh=name_zh,
                    name_en=name_en,
                    is_system=is_system,
                    is_editable=is_editable,
                    bypass_row_level_security=bypass,
                    sort_order=sort,
                ))
        await db.flush()

        # ─── Ensure system user exists (for PLM background task FKs) ───
        system_user_result = await db.execute(
            select(User).where(User.user_id == SYSTEM_USER_ID)
        )
        if not system_user_result.scalar_one_or_none():
            # Guard: skip system user creation if admin role is missing
            admin_role_result = await db.execute(
                select(RoleDefinition).where(RoleDefinition.role_key == "admin")
            )
            admin_role_row = admin_role_result.scalar_one_or_none()
            if admin_role_row is None:
                print("WARNING: admin role not found, skipping system user creation.")
            else:
                db.add(User(
                    user_id=SYSTEM_USER_ID,
                    username="system",
                    display_name="System",
                    email="system@openqms.local",
                    # System user is FK-only and should never login
                    password_hash=hash_password(secrets.token_urlsafe()),
                    legacy_role="admin",
                    role_id=admin_role_row.id,
                    is_active=True,
                ))
                await db.flush()
                print("System user created for PLM background tasks.")

        # Check if already seeded
        result = await db.execute(select(User).where(User.username == "engineer"))
        if result.scalar_one_or_none():
            print("Core data already seeded, running Phase 2 module seed data only.")
            # Fetch existing IDs for Phase 2 seed functions
            admin_result = await db.execute(select(User).where(User.username == "admin"))
            admin_user = admin_result.scalar_one()
            admin_id = admin_user.user_id
            engineer_user = (await db.execute(select(User).where(User.username == "engineer"))).scalar_one()
            manager_user = (await db.execute(select(User).where(User.username == "manager"))).scalar_one()

            fmea_result = await db.execute(select(FMEADocument))
            fmeas = list(fmea_result.scalars().all())
            fmea1 = next((f for f in fmeas if f.document_no == "PFMEA-2026-001"), fmeas[0] if fmeas else None)
            fmea3 = next((f for f in fmeas if f.document_no == "DFMEA-2026-001"), None)

            capa_result = await db.execute(select(CAPAEightD))
            capa1 = capa_result.scalars().first()

            from app.models.supplier import Supplier
            supplier_result = await db.execute(select(Supplier).order_by(Supplier.supplier_no))
            suppliers = list(supplier_result.scalars().all())
            supplier1 = suppliers[0] if len(suppliers) > 0 else None
            supplier2 = suppliers[1] if len(suppliers) > 1 else None

            from app.models.iqc_material import IqcMaterial
            iqc_materials_list = list((await db.execute(select(IqcMaterial))).scalars().all())

            from app.models.factory import Factory
            default_factory = (await db.execute(
                select(Factory).where(Factory.code == "DEFAULT")
            )).scalar_one()

            # ── Phase 2: Additional module seed data ──
            gauges = await seed_gauges(db, admin_id, default_factory.id)
            spc_chars = await seed_spc(db, admin_id, engineer_user.user_id, default_factory.id,
                                        fmea1.fmea_id if fmea1 else None,
                                        capa1.report_id if capa1 else None)
            if gauges and spc_chars:
                await seed_msa(db, admin_id, default_factory.id, gauges, spc_chars)
            await seed_iqc_inspections(db, admin_id, default_factory.id,
                                        supplier1.supplier_id if supplier1 else None,
                                        iqc_materials_list, capa1_id=capa1.report_id if capa1 else None)
            if fmea1:
                await seed_control_plans(db, admin_id, manager_user.user_id, default_factory.id, fmea1.fmea_id)
            await seed_audits(db, admin_id, engineer_user.user_id, manager_user.user_id, default_factory.id,
                              capa1_id=capa1.report_id if capa1 else None)
            if supplier1 and supplier2:
                await seed_ppap(db, admin_id, manager_user.user_id, default_factory.id,
                                supplier1.supplier_id, supplier2.supplier_id)
            await seed_quality_goals(db, admin_id, engineer_user.user_id, manager_user.user_id, default_factory.id)
            if supplier1 and supplier2:
                await seed_scars(db, admin_id, engineer_user.user_id, default_factory.id,
                                supplier1.supplier_id, supplier2.supplier_id,
                                capa1_id=capa1.report_id if capa1 else None)
            await seed_mes_mock(db, admin_id, default_factory.id)
            await seed_erp_mock(db, admin_id, default_factory.id)
            await seed_apqp(db, admin_id, engineer_user.user_id, default_factory.id,
                           fmea1.fmea_id if fmea1 else None,
                           fmea3_id=fmea3.fmea_id if fmea3 else None)

            await db.commit()
            print("Phase 2 seed data created successfully!")
            return

        # Load roles
        role_result = await db.execute(select(RoleDefinition))
        roles = {r.role_key: r.id for r in role_result.scalars().all()}

        # Admin user (may already exist from lifespan bootstrap)
        admin_result = await db.execute(select(User).where(User.username == "admin"))
        admin = admin_result.scalar_one_or_none()
        if not admin:
            admin = User(
                username="admin", display_name="系统管理员",
                password_hash=hash_password("Admin@2026"),
                role_id=roles["admin"],
            )
            db.add(admin)
            await db.flush()

        # Users
        engineer = User(
            username="engineer", display_name="质量工程师",
            password_hash=hash_password("Engineer@2026"), role_id=roles["field_qe"],
        )
        manager = User(
            username="manager", display_name="质量经理",
            password_hash=hash_password("Manager@2026"), role_id=roles["manager"],
        )
        viewer = User(
            username="viewer", display_name="只读用户",
            password_hash=hash_password("Viewer@2026"), role_id=roles["viewer"],
        )
        db.add_all([engineer, manager, viewer])
        await db.flush()

        # Product types (cross-factory taxonomy)
        from app.models.product_type import ProductType
        pt_data = [
            {"code": "POWER", "name": "电源类", "description": "电源模块/电源线", "is_active": True},
            {"code": "PCB", "name": "PCB 类", "description": "印制电路板/贴片线", "is_active": True},
        ]
        for pt_dict in pt_data:
            existing = await db.execute(select(ProductType).where(ProductType.code == pt_dict["code"]))
            if not existing.scalar_one_or_none():
                db.add(ProductType(**pt_dict))
        await db.flush()

        # Product lines (must exist before UserProductLine assignments)
        from app.models.product_line import ProductLine
        pl_data = [
            {"code": "DC-DC-100", "name": "DC-DC 100W 电源模块", "product_type_code": "POWER"},
            {"code": "PCB-SMT-200", "name": "PCB SMT 200 贴片线", "product_type_code": "PCB"},
        ]
        for pl_dict in pl_data:
            existing = await db.execute(select(ProductLine).where(ProductLine.code == pl_dict["code"]))
            if not existing.scalar_one_or_none():
                db.add(ProductLine(**pl_dict))
        await db.flush()

        # Product line assignments
        db.add(UserProductLine(user_id=engineer.user_id, product_line_code="DC-DC-100"))
        db.add(UserProductLine(user_id=manager.user_id, product_line_code="DC-DC-100"))
        db.add(UserProductLine(user_id=viewer.user_id, product_line_code="DC-DC-100"))

        # FMEA documents
        fmea1 = FMEADocument(
            document_no="PFMEA-2026-001", title="SMT焊接工序PFMEA",
            fmea_type="PFMEA", status="approved",
            graph_data=SAMPLE_GRAPH,
            created_by=engineer.user_id, updated_by=engineer.user_id,
            approved_by=manager.user_id,
            approved_at=datetime.now(UTC),
        )
        fmea2 = FMEADocument(
            document_no="PFMEA-2026-002", title="注塑工序PFMEA",
            fmea_type="PFMEA", status="draft",
            graph_data={"nodes": [
                {"id": "pi_draft", "type": "ProcessItem", "name": "新建过程项目", "severity": 0, "occurrence": 0, "detection": 0}
            ], "edges": []},
            created_by=engineer.user_id, updated_by=engineer.user_id,
        )
        fmea3 = FMEADocument(
            document_no="DFMEA-2026-001", title="电池管理系统 (BMS) DFMEA",
            fmea_type="DFMEA", status="in_review",
            graph_data=SAMPLE_DFMEA_GRAPH,
            created_by=engineer.user_id, updated_by=engineer.user_id,
        )
        db.add_all([fmea1, fmea2, fmea3])
        await db.flush()

        # CAPA reports
        capa1 = CAPAEightD(
            document_no="8D-2026-001", title="焊接不良客诉",
            status="D4_ROOT_CAUSE", severity="serious",
            d1_team=[{"name": "张三", "role": "质量工程师"}, {"name": "李四", "role": "工艺工程师"}],
            d2_description="客户反馈PCB组件焊接不良，影响数量500pcs",
            d3_interim="已隔离不良批次，100%加检",
            d4_root_cause="初步判断为回流焊温度曲线异常",
            due_date=date(2026, 6, 1),
            fmea_ref_id=fmea1.fmea_id,
            created_by=engineer.user_id,
        )
        capa2 = CAPAEightD(
            document_no="8D-2026-002", title="注塑尺寸超差",
            status="D1_TEAM", severity="general",
            d1_team=[],
            due_date=date(2026, 6, 15),
            created_by=engineer.user_id,
        )
        db.add_all([capa1, capa2])

        # --- Management Review seed data ---
        # Historical closed review (for previous_review_outputs stats)
        review1 = ManagementReview(
            doc_no="MR-2026-001",
            title="2026年Q1全厂管理评审",
            review_date=date(2026, 3, 15),
            actual_date=date(2026, 3, 16),
            status="closed",
            product_line_code=None,  # 全厂级
            location="质量会议室",
            chair_person_id=manager.user_id,
            participants=[
                {"user_id": str(engineer.user_id), "name": "质量工程师", "role": "记录员", "department": "质量部"},
                {"user_id": str(manager.user_id), "name": "质量经理", "role": "主持人", "department": "质量部"},
            ],
            meeting_minutes="评审确认质量目标达成率良好，FMEA风险控制有效。决定加强供应商绩效监控。",
            data_package={
                "generated_at": "2026-03-15T09:00:00Z",
                "quality_goals": {"total": 10, "achieved": 7, "on_track": 2, "behind": 1},
                "capa_stats": {"total": 25, "open": 8, "closed": 17},
            },
            created_by=engineer.user_id,
            updated_by=manager.user_id,
        )
        db.add(review1)
        await db.flush()

        # Outputs for historical review (verified for completion rate stats)
        output1_v = ReviewOutput(
            review_id=review1.review_id,
            category="improvement_opportunity",
            description="建立供应商绩效看板，每周更新评级分布",
            responsible_id=engineer.user_id,
            due_date=date(2026, 4, 30),
            status="verified",
            completion_notes="已开发供应商绩效看板模块，并完成首周数据录入",
            verified_by=manager.user_id,
            verified_at=date(2026, 5, 10),
            verification_notes="看板运行稳定，数据准确，达到预期效果",
        )
        output2_v = ReviewOutput(
            review_id=review1.review_id,
            category="system_change",
            description="修订采购程序文件，增加供应商准入审批流程",
            responsible_id=manager.user_id,
            due_date=date(2026, 5, 15),
            status="verified",
            completion_notes="已完成程序文件修订，培训相关人员",
            verified_by=manager.user_id,
            verified_at=date(2026, 5, 20),
            verification_notes="文件审批完成，培训记录完整",
        )
        output3_c = ReviewOutput(
            review_id=review1.review_id,
            category="resource_need",
            description="增配一台SPC统计分析工作站",
            responsible_id=engineer.user_id,
            due_date=date(2026, 6, 1),
            status="completed",
            completion_notes="设备已采购到位，安装调试完成",
        )
        db.add_all([output1_v, output2_v, output3_c])

        # Current in-review review
        review2 = ManagementReview(
            doc_no="MR-2026-002",
            title="DC-DC-100产品线Q2管理评审",
            review_date=date(2026, 5, 28),
            status="in_review",
            product_line_code="DC-DC-100",
            location="生产线会议室",
            chair_person_id=manager.user_id,
            participants=[
                {"user_id": str(engineer.user_id), "name": "质量工程师", "role": "数据准备", "department": "质量部"},
            ],
            created_by=engineer.user_id,
        )
        db.add(review2)
        await db.flush()

        output4_p = ReviewOutput(
            review_id=review2.review_id,
            category="improvement_opportunity",
            description="优化SPC控制限设定，缩短Cpk达标周期",
            responsible_id=engineer.user_id,
            due_date=date(2026, 7, 15),
            status="pending",
        )
        db.add(output4_p)

        # --- Special Characteristics seed data ---
        from app.models.special_characteristic import SpecialCharacteristic

        admin_result = await db.execute(select(User).where(User.username == "admin"))
        admin_id = admin_result.scalar_one().user_id

        sc_data = [
            {
                "sc_code": "SC-2026-001",
                "sc_name": "空载转速偏差",
                "sc_type": "CC",
                "customer_symbol": "🛡️",
                "sc_category": "product",
                "spec_requirement": "空载转速 3500±50 RPM",
                "source_fmea_id": fmea1.fmea_id,
                "source_node_id": "psf_1",
                "source_type": "PFMEA",
                "product_line_code": "DC-DC-100",
                "msa_status": "PASS",
                "sop_ref": "SOP-09",
                "is_supplier_shared": True,
                "supplier_code": "SUP-08",
            },
            {
                "sc_code": "SC-2026-002",
                "sc_name": "压装扭矩",
                "sc_type": "SC",
                "customer_symbol": "(S)",
                "sc_category": "process",
                "spec_requirement": "压装扭矩 25±2 Nm",
                "source_fmea_id": fmea1.fmea_id,
                "source_node_id": "wef_1",
                "source_type": "PFMEA",
                "product_line_code": "DC-DC-100",
                "msa_status": "PENDING",
            },
        ]

        for sc_dict in sc_data:
            existing = await db.execute(
                select(SpecialCharacteristic).where(SpecialCharacteristic.sc_code == sc_dict["sc_code"])
            )
            if not existing.scalar_one_or_none():
                sc = SpecialCharacteristic(**sc_dict, created_by=admin_id)
                db.add(sc)

        # Product lines
        from app.models.product_line import ProductLine

        pl_data = [
            {"code": "DC-DC-100", "name": "DC-DC 100W 电源模块", "product_type_code": "POWER"},
            {"code": "PCB-SMT-200", "name": "PCB SMT 200 贴片线", "product_type_code": "PCB"},
        ]
        for pl_dict in pl_data:
            existing = await db.execute(select(ProductLine).where(ProductLine.code == pl_dict["code"]))
            if not existing.scalar_one_or_none():
                db.add(ProductLine(**pl_dict))

        # IQC demo materials
        from app.models.iqc_material import IqcMaterial

        iqc_materials = [
            {
                "part_no": "RES-0805-10K",
                "part_name": "0805贴片电阻 10KΩ ±1%",
                "part_spec": "±1% 1/8W",
                "material_type": "component",
                "default_aql": 0.65,
                "default_inspection_level": "II",
                "unit": "pcs",
                "product_line_code": "DC-DC-100",
            },
            {
                "part_no": "CAP-0805-10U",
                "part_name": "0805贴片电容 10uF ±20%",
                "part_spec": "±20% 16V",
                "material_type": "component",
                "default_aql": 1.0,
                "default_inspection_level": "II",
                "unit": "pcs",
                "product_line_code": "DC-DC-100",
            },
            {
                "part_no": "PCB-DC-001",
                "part_name": "DC-DC电源模块PCB板",
                "part_spec": "FR-4 1.6mm 双层板",
                "material_type": "raw",
                "default_aql": 0.4,
                "default_inspection_level": "II",
                "unit": "pcs",
                "product_line_code": "DC-DC-100",
            },
        ]
        for mat_dict in iqc_materials:
            existing = await db.execute(select(IqcMaterial).where(IqcMaterial.part_no == mat_dict["part_no"]))
            if not existing.scalar_one_or_none():
                db.add(IqcMaterial(created_by=admin_id, **mat_dict))

        await db.flush()

        # --- Customer Quality seed data ---
        customer1 = Customer(
            customer_code="CUS-001",
            name="上海新能源主机厂",
            segment="汽车",
            contact_name="王工",
            contact_email="wang.quality@example.com",
            contact_phone="021-55550001",
            csr_list=[
                {"title": "24小时初步响应", "description": "重大质量问题需24小时内给出初步回复"},
                {"title": "批次追溯", "description": "所有客诉需提供生产批次与围堵记录"},
            ],
            ppm_target=100.0,
            annual_shipment_qty=36500,
            notes="重点汽车客户，月度质量例会",
            created_by=engineer.user_id,
        )
        customer2 = Customer(
            customer_code="CUS-002",
            name="苏州工业控制有限公司",
            segment="工业",
            contact_name="赵经理",
            contact_email="zhao.qa@example.com",
            contact_phone="0512-55550002",
            csr_list=[{"title": "包装标识", "description": "外箱需标识产品批号和检验状态"}],
            ppm_target=250.0,
            annual_shipment_qty=18000,
            notes="工业控制器客户",
            created_by=engineer.user_id,
        )
        db.add_all([customer1, customer2])
        await db.flush()

        attachment_photo = [
            {
                "file_name": "defect-photo.jpg",
                "file_url": "https://example.com/defect-photo.jpg",
                "uploaded_at": "2026-05-26T10:00:00Z",
                "uploaded_by": "seed",
                "category": "photo",
            }
        ]
        attachment_report = [
            {
                "file_name": "rma-analysis.pdf",
                "file_url": "https://example.com/rma-analysis.pdf",
                "uploaded_at": "2026-05-25T15:30:00Z",
                "uploaded_by": "seed",
                "category": "analysis_report",
            }
        ]

        complaint1 = CustomerComplaint(
            complaint_no="CC-2026-001",
            product_line_code="DC-DC-100",
            customer_id=customer1.customer_id,
            product_id="DCDC-100W-A",
            batch_no="B20260518-01",
            serial_number="SN-DCDC-20260518-0007",
            category="safety",
            severity="致命",
            defect_desc="客户现场反馈电源模块异常发热并触发整车报警",
            impact_qty=12,
            occurred_date=date(2026, 5, 24),
            received_date=date(2026, 5, 26),
            due_date=date(2026, 5, 27),
            status="open",
            fmea_ref_id=fmea1.fmea_id,
            capa_ref_id=capa1.report_id,
            has_rma=True,
            preliminary_response=None,
            root_cause=None,
            corrective_action=None,
            attachments=attachment_photo,
            assignee_id=engineer.user_id,
            supplier_responsibility=False,
            created_by=engineer.user_id,
        )
        complaint2 = CustomerComplaint(
            complaint_no="CC-2026-002",
            product_line_code="DC-DC-100",
            customer_id=customer1.customer_id,
            product_id="DCDC-100W-A",
            batch_no="B20260510-03",
            category="function",
            severity="严重",
            defect_desc="客户抽检发现输出电压间歇性漂移",
            impact_qty=35,
            occurred_date=date(2026, 5, 18),
            received_date=date(2026, 5, 20),
            due_date=date(2026, 5, 23),
            status="investigating",
            fmea_ref_id=fmea1.fmea_id,
            preliminary_response="已启动批次围堵并安排样件回收分析",
            attachments=attachment_photo,
            assignee_id=engineer.user_id,
            supplier_responsibility=False,
            created_by=engineer.user_id,
        )
        complaint3 = CustomerComplaint(
            complaint_no="CC-2026-003",
            product_line_code="PCB-SMT-200",
            customer_id=customer2.customer_id,
            product_id="PCB-CTRL-200",
            batch_no="SMT20260428-02",
            category="appearance",
            severity="一般",
            defect_desc="客户反馈外观轻微划伤，未影响功能",
            impact_qty=8,
            occurred_date=date(2026, 4, 29),
            received_date=date(2026, 5, 2),
            due_date=date(2026, 5, 12),
            status="closed",
            preliminary_response="已确认包装隔板磨损导致，完成改善",
            root_cause="周转箱隔板磨损后保护不足",
            corrective_action="更换隔板并增加出货外观复检",
            attachments=attachment_report,
            assignee_id=engineer.user_id,
            supplier_responsibility=False,
            closed_at=datetime(2026, 5, 10, tzinfo=UTC),
            created_by=engineer.user_id,
        )
        db.add_all([complaint1, complaint2, complaint3])
        await db.flush()

        rma1 = RMARecord(
            rma_no="RMA-2026-001",
            product_line_code="DC-DC-100",
            customer_id=customer1.customer_id,
            complaint_id=complaint1.complaint_id,
            product_id="DCDC-100W-A",
            batch_no="B20260518-01",
            serial_number="SN-DCDC-20260518-0007",
            return_qty=5,
            defect_type="功能不良",
            responsibility="internal",
            analysis_result="待完成电气复测与热分析",
            corrective_action="已隔离同批次库存并暂停发运",
            status="analysis",
            fmea_ref_id=fmea1.fmea_id,
            capa_ref_id=capa1.report_id,
            attachments=attachment_report,
            assignee_id=engineer.user_id,
            tracking_number="SF123456789CN",
            received_date=date(2026, 5, 26),
            created_by=engineer.user_id,
        )
        rma2 = RMARecord(
            rma_no="RMA-2026-002",
            product_line_code="PCB-SMT-200",
            customer_id=customer2.customer_id,
            product_id="PCB-CTRL-200",
            batch_no="SMT20260505-01",
            return_qty=3,
            defect_type="外观缺陷",
            responsibility="transport",
            analysis_result="外箱挤压导致边角划伤",
            corrective_action="通知物流更换缓冲包装",
            status="closed",
            attachments=attachment_report,
            assignee_id=engineer.user_id,
            tracking_number="DHL-20260520-0002",
            received_date=date(2026, 5, 21),
            closed_at=datetime(2026, 5, 25, tzinfo=UTC),
            created_by=engineer.user_id,
        )
        db.add_all([rma1, rma2])

        # ─── Supplier seed data ───
        from app.models.supplier import Supplier, SupplierEvaluation
        supplier1 = Supplier(
            supplier_no="SUP-2026-001",
            name="测试供应商A",
            short_name="供应商A",
            contact_name="李经理",
            contact_phone="021-55551001",
            contact_email="li.supplier@example.com",
            address="上海市浦东新区张江高科技园区",
            product_scope="电子元器件、PCB板",
            status="approved",
            created_by=admin.user_id,
        )
        supplier2 = Supplier(
            supplier_no="SUP-2026-002",
            name="测试供应商D",
            short_name="供应商D",
            contact_name="张工",
            contact_phone="0512-55552002",
            contact_email="zhang.supplier@example.com",
            address="苏州市工业园区",
            product_scope="结构件、包装材料",
            status="approved",
            created_by=admin.user_id,
        )
        db.add_all([supplier1, supplier2])
        await db.flush()

        # Supplier evaluations
        eval1 = SupplierEvaluation(
            supplier_id=supplier1.supplier_id,
            eval_period="2026-Q1",
            eval_type="quarterly",
            quality_score=92.0,
            delivery_score=95.0,
            service_score=88.0,
            total_score=91.5,
            grade="A",
            notes="供应商表现优秀，按时交付且质量稳定",
            evaluated_by=admin.user_id,
        )
        eval2 = SupplierEvaluation(
            supplier_id=supplier2.supplier_id,
            eval_period="2026-Q1",
            eval_type="quarterly",
            quality_score=78.0,
            delivery_score=82.0,
            service_score=75.0,
            capa_count=1,
            capa_penalty=5.0,
            total_score=78.5,
            grade="B",
            notes="供应商表现一般，存在一次CAPA需关注",
            evaluated_by=admin.user_id,
        )
        db.add_all([eval1, eval2])

        # ─── Shipment records seed ───
        from datetime import date as date_type
        from datetime import timedelta

        # Pre-fetch default factory for records that need factory_id
        default_factory = (await db.execute(
            select(Factory).where(Factory.code == "DEFAULT")
        )).scalar_one_or_none()
        if not default_factory:
            # If running on fresh DB where migration hasn't created it, create it
            default_factory = Factory(code="DEFAULT", name="默认工厂", location="总部", is_active=True)
            db.add(default_factory)
            await db.flush()

        for customer in [customer1, customer2]:
            for i in range(6):
                db.add(ShipmentRecord(
                    shipment_id=uuid.uuid4(),
                    customer_id=customer.customer_id,
                    product_line_code="DC-DC-100",
                    factory_id=default_factory.id,
                    shipment_date=date_type.today() - timedelta(days=i * 15),
                    quantity=(i + 1) * 500,
                    batch_no=f"BATCH-SHIP-2026-{i+1:03d}",
                    destination="上海",
                    notes=f"发运记录 {i+1}",
                ))

        # ─── Warranty records seed ───
        for customer in [customer1, customer2]:
            for i in range(3):
                db.add(WarrantyRecord(
                    warranty_id=uuid.uuid4(),
                    customer_id=customer.customer_id,
                    product_line_code="DC-DC-100",
                    factory_id=default_factory.id,
                    claim_date=date_type.today() - timedelta(days=i * 60),
                    amount=(i + 1) * 3500.0,
                    failure_mode="短路" if i == 0 else ("开路" if i == 1 else "参数漂移"),
                    description=f"保修索赔 {i+1} - {customer.name}",
                ))

        # ─── PLM demo data ───
        from app.models.plm import PLMConnection
        from app.services.plm_connector import MockPLMConnector
        from app.services.plm_service import PLMIngestionService

        existing_conn = await db.execute(
            select(PLMConnection).where(PLMConnection.name == "DC-DC PLM (Mock)")
        )
        if not existing_conn.scalar_one_or_none():
            plm_conn = PLMConnection(
                name="DC-DC PLM (Mock)",
                connector_type="mock",
                product_line_code="DC-DC-100",
                config={},
                is_active=True,
                created_by=SYSTEM_USER_ID,
            )
            db.add(plm_conn)
            await db.flush()

            mock_connector = MockPLMConnector()
            ingestion = PLMIngestionService(db)
            epoch = datetime(2020, 1, 1, tzinfo=UTC)

            for part in await mock_connector.fetch_parts(epoch):
                part["data_type"] = "part"
                part["connection_id"] = plm_conn.connection_id
                part["product_line_code"] = plm_conn.product_line_code
                try:
                    await ingestion.ingest(part)
                except Exception as e:
                    print(f"WARNING: failed to ingest PLM part {part.get('part_number', '?')}: {e}")

            for bom in await mock_connector.fetch_boms(epoch):
                bom["data_type"] = "bom"
                bom["connection_id"] = plm_conn.connection_id
                bom["product_line_code"] = plm_conn.product_line_code
                try:
                    await ingestion.ingest(bom)
                except Exception as e:
                    print(f"WARNING: failed to ingest PLM BOM {bom.get('external_id', '?')}: {e}")

            for co in await mock_connector.fetch_change_orders(epoch):
                co["data_type"] = "change_order"
                co["connection_id"] = plm_conn.connection_id
                co["product_line_code"] = plm_conn.product_line_code
                try:
                    await ingestion.ingest(co)
                except Exception as e:
                    print(f"WARNING: failed to ingest PLM change order {co.get('change_number', '?')}: {e}")

            print("PLM demo data seeded (mock connector).")

        # ─── Full permission matrix ───
        await seed_all_permissions(db)

        # ─── Supplier risk default configs ───
        await seed_supplier_risk_configs(db)

        # ─── Supply chain risk map snapshots ───
        await seed_supply_chain_risk_snapshots(db)

        # ─── Multi-factory seed data ───
        from app.models.product_line import ProductLine

        # Second factory
        shanghai_factory = Factory(
            code="SH-02",
            name="上海工厂",
            location="上海市浦东新区",
            is_active=True,
        )
        db.add(shanghai_factory)
        await db.flush()

        # default_factory was already fetched earlier (for shipment/warranty records)

        # Assign DC-DC-100 product line to default factory
        await db.execute(
            text("UPDATE product_lines SET factory_id = :factory_id WHERE code = 'DC-DC-100'"),
            {"factory_id": default_factory.id}
        )
        # Assign PCB-SMT-200 product line to default factory
        await db.execute(
            text("UPDATE product_lines SET factory_id = :factory_id WHERE code = 'PCB-SMT-200'"),
            {"factory_id": default_factory.id}
        )

        # New product line for Shanghai factory
        sh_product_line = ProductLine(
            code="SH-DC-200",
            name="上海DC-DC 200W",
            is_active=True,
            factory_id=shanghai_factory.id,
        )
        db.add(sh_product_line)

        # ─── Set factory_id on FMEA/CAPA records created earlier ───
        await db.execute(
            text("UPDATE fmea_documents SET factory_id = :fid WHERE factory_id IS NULL"),
            {"fid": default_factory.id}
        )
        await db.execute(
            text("UPDATE capa_eightd SET factory_id = :fid WHERE factory_id IS NULL"),
            {"fid": default_factory.id}
        )

        # Assign existing users to factories
        admin = (await db.execute(select(User).where(User.username == "admin"))).scalar_one()
        manager_user = (await db.execute(select(User).where(User.username == "manager"))).scalar_one()
        engineer_user = (await db.execute(select(User).where(User.username == "engineer"))).scalar_one()
        viewer_user = (await db.execute(select(User).where(User.username == "viewer"))).scalar_one()

        db.add(UserFactory(user_id=admin.user_id, factory_id=default_factory.id))
        db.add(UserFactory(user_id=admin.user_id, factory_id=shanghai_factory.id))
        db.add(UserFactory(user_id=manager_user.user_id, factory_id=default_factory.id))
        db.add(UserFactory(user_id=manager_user.user_id, factory_id=shanghai_factory.id))
        db.add(UserFactory(user_id=engineer_user.user_id, factory_id=default_factory.id))
        db.add(UserFactory(user_id=viewer_user.user_id, factory_id=default_factory.id))

        # Set default factory for existing users
        admin.factory_id = default_factory.id
        manager_user.factory_id = default_factory.id
        engineer_user.factory_id = default_factory.id
        viewer_user.factory_id = default_factory.id

        # Group admin user
        group_admin = User(
            username="groupadmin",
            display_name="集团管理员",
            email="groupadmin@qms.example.com",
            password_hash=hash_password("GroupAdmin@2026"),
            role_id=admin.role_id,  # same role as admin
            is_active=True,
        )
        db.add(group_admin)
        await db.flush()

        # Assign group admin to both factories (no default factory = group user)
        db.add(UserFactory(user_id=group_admin.user_id, factory_id=default_factory.id))
        db.add(UserFactory(user_id=group_admin.user_id, factory_id=shanghai_factory.id))

        # Ensure admin role has GROUP ADMIN permission
        admin_role = (await db.execute(
            select(RoleDefinition).where(RoleDefinition.role_key == "admin")
        )).scalar_one()
        manager_role = (await db.execute(
            select(RoleDefinition).where(RoleDefinition.role_key == "manager")
        )).scalar_one()

        existing_group_admin = (await db.execute(
            select(RolePermission).where(
                RolePermission.role_id == admin_role.id,
                RolePermission.module == "group"
            )
        )).scalar_one_or_none()
        if not existing_group_admin:
            db.add(RolePermission(role_id=admin_role.id, module="group", permission_level=5))

        existing_group_manager = (await db.execute(
            select(RolePermission).where(
                RolePermission.role_id == manager_role.id,
                RolePermission.module == "group"
            )
        )).scalar_one_or_none()
        if not existing_group_manager:
            db.add(RolePermission(role_id=manager_role.id, module="group", permission_level=3))

        # ═════════════════════════════════════════════════════════════════
        # Phase 2: Additional module seed data
        # ═════════════════════════════════════════════════════════════════

        # ─── Gauges & Calibrations ───
        gauges = await seed_gauges(db, admin_id, default_factory.id)

        # ─── SPC (Inspection Characteristics, Samples, Control Limits) ───
        spc_chars = await seed_spc(db, admin_id, engineer.user_id, default_factory.id, fmea1.fmea_id, capa1.report_id)

        # ─── MSA (GRR, Bias, Linearity, Stability) ───
        if gauges and spc_chars:
            await seed_msa(db, admin_id, default_factory.id, gauges, spc_chars)

        # ─── IQC Inspections (Templates, Inspections, Items) ───
        # Refresh IQC materials from DB (they were created earlier)
        iqc_material_results = (await db.execute(select(IqcMaterial))).scalars().all()
        iqc_materials_list = list(iqc_material_results)
        await seed_iqc_inspections(
            db, admin_id, default_factory.id, supplier1.supplier_id,
            iqc_materials_list, capa1_id=capa1.report_id,
        )

        # ─── Control Plans ───
        await seed_control_plans(db, admin_id, manager.user_id, default_factory.id, fmea1.fmea_id)

        # ─── Audit Programs, Plans, Findings ───
        await seed_audits(db, admin_id, engineer.user_id, manager.user_id, default_factory.id, capa1_id=capa1.report_id)

        # ─── PPAP Submissions ───
        await seed_ppap(db, admin_id, manager.user_id, default_factory.id, supplier1.supplier_id, supplier2.supplier_id)

        # ─── Quality Goals ───
        await seed_quality_goals(db, admin_id, engineer.user_id, manager.user_id, default_factory.id)

        # ─── SCAR Records ───
        await seed_scars(db, admin_id, engineer.user_id, default_factory.id, supplier1.supplier_id, supplier2.supplier_id, capa1_id=capa1.report_id)

        # ─── MES Mock Data ───
        await seed_mes_mock(db, admin_id, default_factory.id)

        # ─── ERP Mock Data ───
        await seed_erp_mock(db, admin_id, default_factory.id)

        # ─── APQP Projects ───
        await seed_apqp(db, admin_id, engineer.user_id, default_factory.id, fmea1.fmea_id, fmea3_id=fmea3.fmea_id)

        await db.commit()

    print("Seed data created successfully!")
    print("Users: admin/Admin@2026, engineer/Engineer@2026, manager/Manager@2026, viewer/Viewer@2026, groupadmin/GroupAdmin@2026")


if __name__ == "__main__":
    asyncio.run(seed())
