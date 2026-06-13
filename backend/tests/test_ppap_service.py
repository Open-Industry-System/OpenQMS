import pytest
import pytest_asyncio
import uuid
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.models.supplier import Supplier, SupplierPPAPSubmission, SupplierPPAPElement
from app.models.user import User
from app.models.audit import AuditLog
from app.models.product_line import ProductLine
from app.models.factory import Factory
from app.database import Base
from app.services import ppap_service

import app.models  # noqa: F401 — ensure all FK-referenced tables are registered
import os
from urllib.parse import urlparse


_DEFAULT_FACTORY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest_asyncio.fixture(scope="function")
async def db():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set; this test requires a dedicated test database")
    db_name = urlparse(url).path.lstrip("/")
    if "_test" not in db_name:
        pytest.skip(f"Database '{db_name}' does not contain '_test'; refusing to run destructive tests")

    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            Factory.__table__.insert().values(id=_DEFAULT_FACTORY_ID, code="TEST", name="Test Factory")
        )
        await conn.execute(
            ProductLine.__table__.insert().values(code="DC-DC-100", name="DC-DC Convert 100W", factory_id=_DEFAULT_FACTORY_ID)
        )
        await conn.commit()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def _make_user(db: AsyncSession, username: str, legacy_role: str = "admin") -> User:
    from app.models.role import RoleDefinition
    from sqlalchemy import select
    result = await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == legacy_role))
    rd = result.scalar_one_or_none()
    if rd is None:
        rd = RoleDefinition(
            role_key=legacy_role,
            name_zh=legacy_role,
            name_en=legacy_role,
            is_system=True,
            is_active=True,
        )
        db.add(rd)
        await db.flush()
    user = User(
        user_id=uuid.uuid4(), username=username, display_name=username,
        legacy_role=legacy_role, role_id=rd.id, password_hash="hash",
        factory_id=_DEFAULT_FACTORY_ID,
    )
    db.add(user)
    await db.commit()
    return user


async def _make_supplier(db: AsyncSession, user: User, supplier_no: str = "SUP-TEST") -> Supplier:
    supplier = Supplier(
        supplier_id=uuid.uuid4(),
        supplier_no=supplier_no,
        name=f"Test Supplier {supplier_no}",
        short_name=supplier_no,
        factory_id=_DEFAULT_FACTORY_ID,
        created_by=user.user_id,
    )
    db.add(supplier)
    await db.commit()
    return supplier


async def _make_ppap(db: AsyncSession, user: User, supplier_id: uuid.UUID, **kwargs) -> SupplierPPAPSubmission:
    return await ppap_service.create_ppap(
        db,
        supplier_id=supplier_id,
        part_no="TEST-PART",
        part_name="Test Part",
        user_id=user.user_id,
        **kwargs,
    )


class TestCreatePPAP:
    async def test_create_basic(self, db: AsyncSession):
        user = await _make_user(db, "ppap_create", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        assert ppap.ppap_no.startswith("PPAP-")
        assert ppap.status == "draft"
        assert ppap.revision == 1
        assert ppap.submission_level == 3
        assert len(ppap.elements) == 18

    async def test_create_with_invalid_supplier(self, db: AsyncSession):
        user = await _make_user(db, "ppap_invalid", "quality_engineer")
        with pytest.raises(ValueError, match="供应商不存在"):
            await _make_ppap(db, user, uuid.uuid4())

    async def test_create_level_1_elements(self, db: AsyncSession):
        user = await _make_user(db, "ppap_l1", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id, submission_level=1)
        assert len([e for e in ppap.elements if e.required]) == 1  # Only element 17 (PSW)


class TestTransition:
    async def test_submit_sets_submission_date(self, db: AsyncSession):
        user = await _make_user(db, "ppap_submit", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        ppap = await ppap_service.transition_ppap(db, ppap, "submit", user.user_id)
        assert ppap.status == "under_review"
        assert ppap.submission_date == date.today()

    async def test_approve_requires_all_required_approved(self, db: AsyncSession):
        user = await _make_user(db, "ppap_appr", "manager")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        await ppap_service.transition_ppap(db, ppap, "submit", user.user_id)
        ppap = await ppap_service.get_ppap(db, ppap.submission_id)
        # Don't approve any elements — should fail
        with pytest.raises(ValueError, match="未批准的必填元素"):
            await ppap_service.transition_ppap(db, ppap, "approve", user.user_id)

    async def test_approve_succeeds_when_elements_approved(self, db: AsyncSession):
        user = await _make_user(db, "ppap_ok", "manager")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        await ppap_service.transition_ppap(db, ppap, "submit", user.user_id)
        ppap = await ppap_service.get_ppap(db, ppap.submission_id)
        # Set all required elements to approved
        for el in ppap.elements:
            if el.required:
                await ppap_service.update_element(db, el, user_id=user.user_id, status="approved")
        ppap = await ppap_service.transition_ppap(db, ppap, "approve", user.user_id)
        assert ppap.status == "approved"
        assert ppap.approved_by == user.user_id

    async def test_approve_rejects_required_not_applicable(self, db: AsyncSession):
        user = await _make_user(db, "ppap_na", "manager")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        await ppap_service.transition_ppap(db, ppap, "submit", user.user_id)
        ppap = await ppap_service.get_ppap(db, ppap.submission_id)
        # Set all required elements to not_applicable instead of approved
        for el in ppap.elements:
            if el.required:
                await ppap_service.update_element(db, el, user_id=user.user_id, status="not_applicable")
        with pytest.raises(ValueError, match="未批准的必填元素"):
            await ppap_service.transition_ppap(db, ppap, "approve", user.user_id)

    async def test_reject_requires_reason(self, db: AsyncSession):
        user = await _make_user(db, "ppap_rej", "manager")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        await ppap_service.transition_ppap(db, ppap, "submit", user.user_id)
        ppap = await ppap_service.get_ppap(db, ppap.submission_id)
        with pytest.raises(ValueError, match="驳回原因不能为空"):
            await ppap_service.transition_ppap(db, ppap, "reject", user.user_id)

    async def test_resubmit_increments_revision(self, db: AsyncSession):
        user = await _make_user(db, "ppap_resub", "quality_engineer")
        manager = await _make_user(db, "ppap_mgr", "manager")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        ppap = await ppap_service.transition_ppap(db, ppap, "submit", user.user_id)
        ppap = await ppap_service.transition_ppap(db, ppap, "reject", manager.user_id, rejection_reason="材料不全")
        assert ppap.status == "rejected"
        assert ppap.rejection_reason == "材料不全"
        ppap = await ppap_service.transition_ppap(db, ppap, "resubmit", user.user_id)
        assert ppap.status == "under_review"
        assert ppap.revision == 2

    async def test_invalid_transition_raises(self, db: AsyncSession):
        user = await _make_user(db, "ppap_bad", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        with pytest.raises(ValueError, match="不允许"):
            await ppap_service.transition_ppap(db, ppap, "approve", user.user_id)


class TestUpdateElement:
    async def test_update_element_sets_reviewer(self, db: AsyncSession):
        user = await _make_user(db, "ppap_el", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        el = ppap.elements[0]
        el = await ppap_service.update_element(db, el, user_id=user.user_id, status="approved")
        assert el.status == "approved"
        assert el.reviewed_by == user.user_id
        assert el.reviewed_at is not None

    async def test_update_element_reset_to_pending_clears_reviewer(self, db: AsyncSession):
        user = await _make_user(db, "ppap_el2", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        el = ppap.elements[0]
        el = await ppap_service.update_element(db, el, user_id=user.user_id, status="approved")
        el = await ppap_service.update_element(db, el, user_id=user.user_id, status="pending")
        assert el.status == "pending"
        assert el.reviewed_by is None
        assert el.reviewed_at is None

    async def test_update_element_rejects_null_status(self, db: AsyncSession):
        user = await _make_user(db, "ppap_el3", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        el = ppap.elements[0]
        with pytest.raises(ValueError, match="元素状态不能为空"):
            await ppap_service.update_element(db, el, user_id=user.user_id, status=None)


class TestUpdatePPAP:
    async def test_update_level_recalculates_required(self, db: AsyncSession):
        user = await _make_user(db, "ppap_upd", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id, submission_level=3)
        # Change from level 3 to level 1 — only element 17 should be required
        ppap = await ppap_service.update_ppap(db, ppap, user_id=user.user_id, submission_level=1)
        ppap = await ppap_service.get_ppap(db, ppap.submission_id)
        required = [e for e in ppap.elements if e.required]
        assert len(required) == 1
        assert required[0].element_no == 17

    async def test_update_only_draft(self, db: AsyncSession):
        user = await _make_user(db, "ppap_upd2", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        ppap = await ppap_service.transition_ppap(db, ppap, "submit", user.user_id)
        with pytest.raises(ValueError, match="草稿"):
            await ppap_service.update_ppap(db, ppap, user_id=user.user_id, part_no="NEW")

    async def test_update_rejects_null_part_name(self, db: AsyncSession):
        user = await _make_user(db, "ppap_null_name", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        with pytest.raises(ValueError, match="零件名称不能为空"):
            await ppap_service.update_ppap(db, ppap, user_id=user.user_id, part_name=None)

    async def test_update_rejects_null_part_no(self, db: AsyncSession):
        user = await _make_user(db, "ppap_null_pn", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        with pytest.raises(ValueError, match="零件号不能为空"):
            await ppap_service.update_ppap(db, ppap, user_id=user.user_id, part_no=None)

    async def test_update_rejects_null_submission_level(self, db: AsyncSession):
        user = await _make_user(db, "ppap_null_sl", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        with pytest.raises(ValueError, match="提交等级不能为空"):
            await ppap_service.update_ppap(db, ppap, user_id=user.user_id, submission_level=None)


class TestDeletePPAP:
    async def test_delete_draft(self, db: AsyncSession):
        user = await _make_user(db, "ppap_del", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        await ppap_service.delete_ppap(db, ppap, user.user_id)
        deleted = await ppap_service.get_ppap(db, ppap.submission_id)
        assert deleted is None

    async def test_delete_non_draft(self, db: AsyncSession):
        user = await _make_user(db, "ppap_del2", "quality_engineer")
        supplier = await _make_supplier(db, user)
        ppap = await _make_ppap(db, user, supplier.supplier_id)
        ppap = await ppap_service.transition_ppap(db, ppap, "submit", user.user_id)
        with pytest.raises(ValueError, match="草稿"):
            await ppap_service.delete_ppap(db, ppap, user.user_id)
