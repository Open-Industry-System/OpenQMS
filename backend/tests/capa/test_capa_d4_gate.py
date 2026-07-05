import uuid
import pytest
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.schemas.capa_verification import VerificationCreate
from app.services.capa_service import advance_capa
from app.services.capa_verification_service import create_verification

pytestmark = pytest.mark.requires_db


async def _make_capa(db, factory_id, user_id, status="D4_ROOT_CAUSE"):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=f"8D-GATE-{uuid.uuid4().hex[:6]}",
        title="t", product_line_code="DC-DC-100", factory_id=factory_id,
        created_by=user_id, status=status, d4_root_cause="rc",
    )
    db.add(capa); await db.flush()
    return capa


@pytest.mark.asyncio
async def test_advance_d4_to_d5_blocked_without_verified(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    with pytest.raises(ValueError, match="已验证根因"):
        await advance_capa(db, capa, admin_user.user_id)


@pytest.mark.asyncio
async def test_advance_d4_to_d5_allowed_with_verified(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    await create_verification(db, capa, VerificationCreate(root_cause_text="rc", is_verified=True), admin_user)
    advanced = await advance_capa(db, capa, admin_user.user_id)
    assert advanced.status == "D5_CORRECTION"


@pytest.mark.asyncio
async def test_advance_d4_to_d5_blocked_with_only_unverified(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    await create_verification(db, capa, VerificationCreate(root_cause_text="rc", is_verified=False), admin_user)
    with pytest.raises(ValueError):
        await advance_capa(db, capa, admin_user.user_id)
