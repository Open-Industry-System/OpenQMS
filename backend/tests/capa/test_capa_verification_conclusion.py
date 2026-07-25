import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.core.permissions import Module
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.factory import Factory
from app.models.product_line import ProductLine
from app.models.role import RoleDefinition, RolePermission
from app.models.user import User
from app.schemas.capa_verification import VerificationCreate, VerificationUpdate
from app.services.capa_verification_service import create_verification, update_verification

pytestmark = pytest.mark.requires_db


async def _make_capa(session, factory_id, user_id, pl_code="DC-DC-100", doc_no="8D-B3-001"):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=doc_no, title="t",
        product_line_code=pl_code, factory_id=factory_id,
        created_by=user_id, status="D4_ROOT_CAUSE",
    )
    session.add(capa)
    await session.flush()
    return capa


async def _committed_admin_and_factory(sessionmaker):
    """在真实提交会话中创建工厂、产品线、管理员角色/权限和用户，供并发测试使用。

    所有标识均使用随机值，避免与 db fixture 创建但未提交的记录或其他测试冲突。
    """
    factory_id = uuid.uuid4()
    pl_code = f"PL-{factory_id.hex[:8]}"
    async with sessionmaker() as s:
        factory = Factory(id=factory_id, code=f"TEST-{factory_id.hex[:8]}", name="Test Factory")
        s.add(factory)
        pl = ProductLine(code=pl_code, name=pl_code, factory_id=factory.id)
        s.add(pl)
        role = RoleDefinition(
            role_key=f"admin_b3_{factory_id.hex[:8]}",
            name_zh="系统管理员", name_en="System Admin",
            is_system=True, is_editable=False, bypass_row_level_security=True,
            sort_order=1, is_active=True,
        )
        s.add(role)
        await s.flush()
        user = User(
            user_id=uuid.uuid4(),
            username=f"test_admin_b3_{factory_id.hex[:8]}",
            display_name="Test Admin B3",
            password_hash="hashed",
            role_id=role.id,
            legacy_role="admin",
            is_active=True,
            factory_id=factory.id,
        )
        s.add(user)
        for module in Module:
            s.add(RolePermission(role_id=role.id, module=module.value, permission_level=5))
        await s.commit()
        await s.refresh(user)
        await s.refresh(factory)
        return factory, user, pl_code


@pytest.mark.asyncio
async def test_create_default_pending_no_increment(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    rec = await create_verification(db, capa, VerificationCreate(root_cause_text="rc"), admin_user)
    assert rec.conclusion == "pending"
    assert rec.is_verified is False
    await db.refresh(capa)
    assert capa.d4_retry_count == 0


@pytest.mark.asyncio
async def test_conclusion_failed_increments_retry_count(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    rec = await create_verification(db, capa, VerificationCreate(root_cause_text="rc"), admin_user)
    await update_verification(db, capa, rec.verification_id,
                              VerificationUpdate(conclusion="failed"), admin_user)
    await db.refresh(capa)
    assert capa.d4_retry_count == 1
    assert rec.conclusion == "failed"
    assert rec.is_verified is False


@pytest.mark.asyncio
async def test_conclusion_passed_no_increment(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    rec = await create_verification(
        db, capa,
        VerificationCreate(root_cause_text="rc", method="measurement", result="ok",
                           evidence_attachments=[{"u": 1}]),
        admin_user,
    )
    await update_verification(db, capa, rec.verification_id,
                              VerificationUpdate(conclusion="passed"), admin_user)
    await db.refresh(capa)
    assert capa.d4_retry_count == 0
    assert rec.is_verified is True


@pytest.mark.asyncio
async def test_failed_no_transition_no_double_count(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    rec = await create_verification(db, capa, VerificationCreate(root_cause_text="rc"), admin_user)
    await update_verification(db, capa, rec.verification_id,
                              VerificationUpdate(conclusion="failed"), admin_user)
    # 再次 failed（无跃迁）→ 不递增
    await update_verification(db, capa, rec.verification_id,
                              VerificationUpdate(result="more"), admin_user)
    await db.refresh(capa)
    assert capa.d4_retry_count == 1


@pytest.mark.asyncio
async def test_same_record_concurrent_failed_increments_once(sessionmaker):
    # 单条 verification 记录并发 conclusion=failed → 仅 +1（verification 行 FOR UPDATE 去重）
    factory, admin_user, pl_code = await _committed_admin_and_factory(sessionmaker)
    doc_no = f"8D-B3-SAME-{uuid.uuid4().hex[:8]}"
    async with sessionmaker() as seed:
        capa = await _make_capa(seed, factory.id, admin_user.user_id, pl_code, doc_no)
        rec = await create_verification(seed, capa, VerificationCreate(root_cause_text="rc"), admin_user)
        rid = rec.verification_id
        cid = capa.report_id
        await seed.commit()

    async def worker():
        async with sessionmaker() as s:
            w_capa = await s.get(CAPAEightD, cid)
            try:
                await update_verification(s, w_capa, rid,
                                          VerificationUpdate(conclusion="failed"), admin_user)
            except Exception:
                await s.rollback()
                raise

    await asyncio.gather(worker(), worker())

    async with sessionmaker() as check:
        c = await check.get(CAPAEightD, cid)
        assert c.d4_retry_count == 1


@pytest.mark.asyncio
async def test_different_records_concurrent_failed_increments_twice(sessionmaker):
    # 同一 CAPA 两条不同 verification 记录并发 failed → +2（capa 行 FOR UPDATE 防跨记录丢计数）
    factory, admin_user, pl_code = await _committed_admin_and_factory(sessionmaker)
    doc_no = f"8D-B3-DIFF-{uuid.uuid4().hex[:8]}"
    async with sessionmaker() as seed:
        capa = await _make_capa(seed, factory.id, admin_user.user_id, pl_code, doc_no)
        r1 = await create_verification(seed, capa, VerificationCreate(root_cause_text="rc1"), admin_user)
        r2 = await create_verification(seed, capa, VerificationCreate(root_cause_text="rc2"), admin_user)
        cid = capa.report_id
        rid1, rid2 = r1.verification_id, r2.verification_id
        await seed.commit()

    async def worker(rid):
        async with sessionmaker() as s:
            w_capa = await s.get(CAPAEightD, cid)
            try:
                await update_verification(s, w_capa, rid,
                                          VerificationUpdate(conclusion="failed"), admin_user)
            except Exception:
                await s.rollback()
                raise

    await asyncio.gather(worker(rid1), worker(rid2))

    async with sessionmaker() as check:
        c = await check.get(CAPAEightD, cid)
        assert c.d4_retry_count == 2


@pytest.mark.asyncio
async def test_create_failed_increments_retry_count(db, default_factory, admin_user):
    # 创建即 failed（罕见但支持）→ 递增
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    rec = await create_verification(
        db, capa,
        VerificationCreate(root_cause_text="rc", method="measurement", result="ng",
                           conclusion="failed"),
        admin_user,
    )
    await db.refresh(capa)
    assert capa.d4_retry_count == 1
    assert rec.conclusion == "failed"
    assert rec.is_verified is False


@pytest.mark.asyncio
async def test_audit_rename_for_passed_and_failed(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    rec = await create_verification(
        db, capa,
        VerificationCreate(root_cause_text="rc", method="measurement", result="ok",
                           evidence_attachments=[{"u": 1}]),
        admin_user,
    )
    await update_verification(db, capa, rec.verification_id,
                              VerificationUpdate(conclusion="passed"), admin_user)
    await update_verification(
        db, capa, rec.verification_id,
        VerificationUpdate(conclusion="failed"), admin_user,
    )
    await db.refresh(capa)
    assert capa.d4_retry_count == 1

    audits = (await db.execute(select(AuditLog).where(
        AuditLog.record_id == capa.report_id,
        AuditLog.action.in_(["D4_VERIFICATION_PASSED", "D4_VERIFICATION_FAILED"])))).scalars().all()
    actions = {a.action for a in audits}
    assert "D4_VERIFICATION_PASSED" in actions
    assert "D4_VERIFICATION_FAILED" in actions
    failed_audit = next(a for a in audits if a.action == "D4_VERIFICATION_FAILED")
    assert "retry_count" in failed_audit.changed_fields
    assert failed_audit.changed_fields["retry_count"] == 1
    # 旧的 RC_VERIFY 不应再出现
    old_audits = (await db.execute(select(AuditLog).where(
        AuditLog.record_id == capa.report_id,
        AuditLog.action == "RC_VERIFY"))).scalars().all()
    assert len(old_audits) == 0


@pytest.mark.asyncio
async def test_passed_requires_details(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    rec = await create_verification(db, capa, VerificationCreate(root_cause_text="rc"), admin_user)
    with pytest.raises(ValueError, match="验证方法|结果|证据"):
        await update_verification(db, capa, rec.verification_id,
                                  VerificationUpdate(conclusion="passed"), admin_user)


@pytest.mark.asyncio
async def test_passed_requires_details_on_create(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    with pytest.raises(ValueError, match="验证方法|结果|证据"):
        await create_verification(
            db, capa,
            VerificationCreate(root_cause_text="rc", conclusion="passed"),
            admin_user,
        )


@pytest.mark.asyncio
async def test_pending_no_conclusion_audit(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    await create_verification(db, capa, VerificationCreate(root_cause_text="rc"), admin_user)
    audits = (await db.execute(select(AuditLog).where(
        AuditLog.record_id == capa.report_id,
        AuditLog.action.in_(["D4_VERIFICATION_PASSED", "D4_VERIFICATION_FAILED"])))).scalars().all()
    assert len(audits) == 0
