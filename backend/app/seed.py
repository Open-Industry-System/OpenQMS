"""
Seed script: creates demo data for development.
Run: docker compose exec backend python -m app.seed
"""
import asyncio
from datetime import date, datetime, timezone
from sqlalchemy import select

from app.database import async_session
from app.models.user import User
from app.models.fmea import FMEADocument
from app.models.capa import CAPAEightD
from app.core.security import hash_password


SAMPLE_GRAPH = {
    "nodes": [
        {"id": "n1", "type": "Process", "name": "SMT贴装", "process_number": "OP10"},
        {"id": "n2", "type": "Function", "name": "元件贴装"},
        {"id": "n3", "type": "FailureMode", "name": "元件偏移", "severity": 7, "occurrence": 4, "detection": 3},
        {"id": "n4", "type": "FailureCause", "name": "贴装压力不足"},
        {"id": "n5", "type": "ControlMeasure", "name": "定期校准贴片机"},
        {"id": "n6", "type": "Process", "name": "回流焊", "process_number": "OP20"},
        {"id": "n7", "type": "Function", "name": "焊接连接"},
        {"id": "n8", "type": "FailureMode", "name": "焊点虚焊", "severity": 8, "occurrence": 3, "detection": 5},
        {"id": "n9", "type": "FailureCause", "name": "回流温度不足"},
        {"id": "n10", "type": "ControlMeasure", "name": "炉温曲线监控"},
    ],
    "edges": [
        {"source": "n1", "target": "n2", "type": "HAS_FUNCTION"},
        {"source": "n2", "target": "n3", "type": "HAS_FAILURE_MODE"},
        {"source": "n3", "target": "n4", "type": "HAS_CAUSE"},
        {"source": "n4", "target": "n5", "type": "CONTROLLED_BY"},
        {"source": "n6", "target": "n7", "type": "HAS_FUNCTION"},
        {"source": "n7", "target": "n8", "type": "HAS_FAILURE_MODE"},
        {"source": "n8", "target": "n9", "type": "HAS_CAUSE"},
        {"source": "n9", "target": "n10", "type": "CONTROLLED_BY"},
    ],
}


async def seed():
    async with async_session() as db:
        # Check if already seeded
        result = await db.execute(select(User).where(User.username == "engineer"))
        if result.scalar_one_or_none():
            print("Already seeded, skipping.")
            return

        # Users
        engineer = User(
            username="engineer", display_name="质量工程师",
            password_hash=hash_password("Engineer@2026"), role="quality_engineer",
        )
        manager = User(
            username="manager", display_name="质量经理",
            password_hash=hash_password("Manager@2026"), role="manager",
        )
        viewer = User(
            username="viewer", display_name="只读用户",
            password_hash=hash_password("Viewer@2026"), role="viewer",
        )
        db.add_all([engineer, manager, viewer])
        await db.flush()

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
            graph_data={"nodes": [], "edges": []},
            created_by=engineer.user_id, updated_by=engineer.user_id,
        )
        db.add_all([fmea1, fmea2])
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
        await db.commit()

    print("Seed data created successfully!")
    print("Users: admin/Admin@2026, engineer/Engineer@2026, manager/Manager@2026, viewer/Viewer@2026")


if __name__ == "__main__":
    asyncio.run(seed())
