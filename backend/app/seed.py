"""
Seed script: creates demo data for development.
Run: docker compose exec backend python -m app.seed
"""
import asyncio
from datetime import date, datetime, timezone, timedelta
from sqlalchemy import select

from app.database import async_session
from app.models.user import User
from app.models.fmea import FMEADocument
from app.models.capa import CAPAEightD
from app.models.management_review import ManagementReview, ReviewOutput
from app.models.customer_quality import Customer, CustomerComplaint, RMARecord, ShipmentRecord, WarrantyRecord
from app.models.role import RoleDefinition, UserProductLine
from app.core.security import hash_password


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


async def seed():
    async with async_session() as db:
        # Check if already seeded
        result = await db.execute(select(User).where(User.username == "engineer"))
        if result.scalar_one_or_none():
            print("Already seeded, skipping.")
            return

        # Load roles
        role_result = await db.execute(select(RoleDefinition))
        roles = {r.role_key: r.id for r in role_result.scalars().all()}

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
            approved_at=datetime.now(timezone.utc),
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
            status="D4_ROOT_CAUSE", severity="严重",
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
            status="D1_TEAM", severity="一般",
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
                "sc_category": "产品特性",
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
                "sc_category": "过程特性",
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
            {"code": "DC-DC-100", "name": "DC-DC 100W 电源模块"},
            {"code": "PCB-SMT-200", "name": "PCB SMT 200 贴片线"},
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
            closed_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
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
            closed_at=datetime(2026, 5, 25, tzinfo=timezone.utc),
            created_by=engineer.user_id,
        )
        db.add_all([rma1, rma2])

        # ─── Supplier seed data ───
        from app.models.supplier import Supplier, SupplierEvaluation
        supplier1 = Supplier(
            supplier_id=uuid.uuid4(),
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
            supplier_id=uuid.uuid4(),
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
            eval_id=uuid.uuid4(),
            supplier_id=supplier1.supplier_id,
            eval_period="2026-Q1",
            eval_type="quarterly",
            quality_score=92.0,
            delivery_score=95.0,
            service_score=88.0,
            capa_count=0,
            finding_count=0,
            premium_freight_count=0,
            customer_disruption_count=0,
            capa_penalty=0.0,
            finding_penalty=0.0,
            premium_freight_penalty=0.0,
            customer_disruption_penalty=0.0,
            total_score=91.5,
            grade="A",
            notes="供应商表现优秀，按时交付且质量稳定",
            evaluated_by=admin.user_id,
        )
        eval2 = SupplierEvaluation(
            eval_id=uuid.uuid4(),
            supplier_id=supplier2.supplier_id,
            eval_period="2026-Q1",
            eval_type="quarterly",
            quality_score=78.0,
            delivery_score=82.0,
            service_score=75.0,
            capa_count=1,
            finding_count=0,
            premium_freight_count=0,
            customer_disruption_count=0,
            capa_penalty=5.0,
            finding_penalty=0.0,
            premium_freight_penalty=0.0,
            customer_disruption_penalty=0.0,
            total_score=78.5,
            grade="B",
            notes="供应商表现一般，存在一次CAPA需关注",
            evaluated_by=admin.user_id,
        )
        db.add_all([eval1, eval2])
        await db.flush()

        # ─── Shipment records seed ───
        from datetime import date as date_type, timedelta
        for customer in [customer1, customer2]:
            for i in range(6):
                db.add(ShipmentRecord(
                    shipment_id=uuid.uuid4(),
                    customer_id=customer.customer_id,
                    product_line_code="DC-DC-100",
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
                    claim_date=date_type.today() - timedelta(days=i * 60),
                    amount=(i + 1) * 3500.0,
                    failure_mode="短路" if i == 0 else ("开路" if i == 1 else "参数漂移"),
                    description=f"保修索赔 {i+1} - {customer.name}",
                ))

        await db.commit()

    print("Seed data created successfully!")
    print("Users: admin/Admin@2026, engineer/Engineer@2026, manager/Manager@2026, viewer/Viewer@2026")


if __name__ == "__main__":
    asyncio.run(seed())
