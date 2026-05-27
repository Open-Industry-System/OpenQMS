import pytest
import pytest_asyncio
import uuid
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.models.apqp import APQPProject
from app.models.user import User
from app.models.audit import AuditLog
from app.models.fmea import FMEADocument
from app.models.control_plan import ControlPlan
from app.models.supplier import Supplier, SupplierPPAPSubmission
from app.models.product_line import ProductLine
from app.database import Base
from app.services import apqp_service

import app.models  # noqa: F401 — ensure all FK-referenced tables are registered in Base.metadata
import os
from urllib.parse import urlparse


def _get_test_db_url():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set; this test requires a dedicated test database", allow_module_level=True)
    db_name = urlparse(url).path.lstrip("/")
    if "_test" not in db_name:
        pytest.skip(f"Database '{db_name}' does not contain '_test'; refusing to run destructive tests", allow_module_level=True)
    return url


TEST_DB_URL = _get_test_db_url()


@pytest_asyncio.fixture(scope="function")
async def db():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            ProductLine.__table__.insert().values(code="DC-DC-100", name="DC-DC Convert 100W")
        )
        await conn.commit()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def _make_user(db: AsyncSession, username: str, role: str) -> User:
    user = User(
        user_id=uuid.uuid4(), username=username, display_name=username,
        role=role, password_hash="hash",
    )
    db.add(user)
    await db.commit()
    return user


async def _make_project(db: AsyncSession, user: User, current_phase: int = 1, **kwargs) -> APQPProject:
    code = f"APQP-2026-TEST-{uuid.uuid4().hex[:6]}"
    proj = APQPProject(
        project_id=uuid.uuid4(), project_code=code,
        project_name="Test", product_name="TestProduct", product_line_code="DC-DC-100",
        created_by=user.user_id, current_phase=current_phase, **kwargs,
    )
    db.add(proj)
    await db.commit()
    return await apqp_service.get_project(db, proj.project_id)


class TestCreateProject:
    async def test_create_basic(self, db: AsyncSession):
        user = await _make_user(db, "test_create", "quality_engineer")
        proj = await apqp_service.create_project(
            db, project_name="APQP Test", product_name="Product X",
            product_line_code="DC-DC-100", user_id=user.user_id,
        )
        assert proj.project_code.startswith("APQP-2026-")
        assert proj.current_phase == 1
        assert proj.phase_status == "in_progress"
        assert proj.project_status == "active"

    async def test_create_with_invalid_dfmea(self, db: AsyncSession):
        user = await _make_user(db, "test_invalid_fk", "quality_engineer")
        fake_id = uuid.uuid4()
        with pytest.raises(ValueError, match="DFMEA"):
            await apqp_service.create_project(
                db, project_name="X", product_name="Y", product_line_code="DC-DC-100",
                user_id=user.user_id, dfmea_id=fake_id,
            )


class TestGateTransitions:
    async def test_submit_gate(self, db: AsyncSession):
        manager = await _make_user(db, "mgr_submit", "manager")
        proj = await _make_project(db, manager)
        proj = await apqp_service.transition_project(
            db, proj, "submit_gate", manager.user_id, manager.display_name,
        )
        assert proj.phase_status == "pending_approval"
        assert proj.gate_history[-1]["action"] == "submit"

    async def test_approve_gate_advances_phase(self, db: AsyncSession):
        manager = await _make_user(db, "mgr_advance", "manager")
        proj = await _make_project(db, manager)
        proj = await apqp_service.transition_project(
            db, proj, "submit_gate", manager.user_id, manager.display_name,
        )
        proj = await apqp_service.transition_project(
            db, proj, "approve_gate", manager.user_id, manager.display_name,
        )
        assert proj.current_phase == 2
        assert proj.phase_status == "in_progress"
        assert proj.phase_1_completed_at is not None

    async def test_approve_gate_requires_submit_first(self, db: AsyncSession):
        manager = await _make_user(db, "mgr_require", "manager")
        proj = await _make_project(db, manager)
        with pytest.raises(ValueError, match="未提交审批"):
            await apqp_service.transition_project(
                db, proj, "approve_gate", manager.user_id, manager.display_name,
            )

    async def test_reject_gate_returns_to_in_progress(self, db: AsyncSession):
        manager = await _make_user(db, "mgr_reject", "manager")
        proj = await _make_project(db, manager)
        proj = await apqp_service.transition_project(
            db, proj, "submit_gate", manager.user_id, manager.display_name,
        )
        proj = await apqp_service.transition_project(
            db, proj, "reject_gate", manager.user_id, manager.display_name,
        )
        assert proj.phase_status == "in_progress"
        assert proj.gate_history[-1]["action"] == "reject"

    async def test_phase_5_approve_completes_project(self, db: AsyncSession):
        manager = await _make_user(db, "mgr_p5", "manager")
        proj = await _make_project(db, manager, current_phase=5)
        await db.commit()
        proj = await apqp_service.get_project(db, proj.project_id)
        proj = await apqp_service.transition_project(
            db, proj, "submit_gate", manager.user_id, manager.display_name,
        )
        proj = await apqp_service.transition_project(
            db, proj, "approve_gate", manager.user_id, manager.display_name,
        )
        assert proj.project_status == "completed"
        assert proj.phase_status == "completed"


class TestDeliverableChecks:
    async def _make_fmea(self, db: AsyncSession, fmea_type: str) -> FMEADocument:
        fmea = FMEADocument(
            fmea_id=uuid.uuid4(), document_no=f"FMEA-TEST-{uuid.uuid4().hex[:6]}",
            title=f"Test {fmea_type}", fmea_type=fmea_type,
            graph_data={"nodes": [], "edges": []},
        )
        db.add(fmea)
        await db.commit()
        return fmea

    async def test_phase_2_missing_dfmea(self, db: AsyncSession):
        manager = await _make_user(db, "mgr_p2_check", "manager")
        proj = await _make_project(db, manager, current_phase=2, dfmea_id=None)
        proj = await apqp_service.transition_project(
            db, proj, "submit_gate", manager.user_id, manager.display_name,
        )
        with pytest.raises(ValueError, match="DFMEA"):
            await apqp_service.transition_project(
                db, proj, "approve_gate", manager.user_id, manager.display_name,
            )

    async def test_phase_2_with_dfmea_passes(self, db: AsyncSession):
        manager = await _make_user(db, "mgr_p2_ok", "manager")
        fmea = await self._make_fmea(db, "DFMEA")
        proj = await _make_project(db, manager, current_phase=2, dfmea_id=fmea.fmea_id)
        proj = await apqp_service.transition_project(
            db, proj, "submit_gate", manager.user_id, manager.display_name,
        )
        proj = await apqp_service.transition_project(
            db, proj, "approve_gate", manager.user_id, manager.display_name,
        )
        assert proj.current_phase == 3

    async def test_phase_3_missing_pfmea(self, db: AsyncSession):
        manager = await _make_user(db, "mgr_p3_check", "manager")
        cp = ControlPlan(cp_id=uuid.uuid4(), document_no=f"CP-TEST-{uuid.uuid4().hex[:6]}",
                         title="Test CP", phase="production")
        db.add(cp)
        await db.commit()
        proj = await _make_project(db, manager, current_phase=3, pfmea_id=None, control_plan_id=cp.cp_id)
        proj = await apqp_service.transition_project(
            db, proj, "submit_gate", manager.user_id, manager.display_name,
        )
        with pytest.raises(ValueError, match="PFMEA"):
            await apqp_service.transition_project(
                db, proj, "approve_gate", manager.user_id, manager.display_name,
            )

    async def test_phase_4_missing_ppap(self, db: AsyncSession):
        manager = await _make_user(db, "mgr_p4_check", "manager")
        proj = await _make_project(db, manager, current_phase=4, ppap_submission_id=None)
        proj = await apqp_service.transition_project(
            db, proj, "submit_gate", manager.user_id, manager.display_name,
        )
        with pytest.raises(ValueError, match="PPAP"):
            await apqp_service.transition_project(
                db, proj, "approve_gate", manager.user_id, manager.display_name,
            )


class TestGuardClauses:
    async def test_completed_project_cannot_transition(self, db: AsyncSession):
        manager = await _make_user(db, "mgr_guard_c", "manager")
        proj = await _make_project(db, manager, project_status="completed", phase_status="completed")
        with pytest.raises(ValueError, match="不在进行中"):
            await apqp_service.transition_project(
                db, proj, "submit_gate", manager.user_id, manager.display_name,
            )

    async def test_cancelled_project_cannot_transition(self, db: AsyncSession):
        manager = await _make_user(db, "mgr_guard_x", "manager")
        proj = await _make_project(db, manager, project_status="cancelled", phase_status="in_progress")
        with pytest.raises(ValueError, match="不在进行中"):
            await apqp_service.transition_project(
                db, proj, "submit_gate", manager.user_id, manager.display_name,
            )


class TestStats:
    async def test_stats_counts(self, db: AsyncSession):
        user = await _make_user(db, "test_stats", "quality_engineer")
        await _make_project(db, user)
        s = await apqp_service.get_stats(db)
        assert s["total_projects"] >= 1
        assert "phase_distribution" in s
