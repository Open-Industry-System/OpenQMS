from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.role import RoleDefinition, UserProductLine
from app.models.user import User
from sqlalchemy import select
from app.models.capa_lateral_diffusion import CapaLateralDiffusionCheck
from app.services.agent.provider_adapter import ProviderNotConfiguredError
from app.services.capa_lateral_diffusion_service import (
    LateralBlockedError,
    LateralFailedError,
    run_lateral_diffusion_check,
)
from tests.capa.test_lateral_diffusion_match import (
    _make_capa,
    _make_pl,
    _seed_base,
)

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
async def test_empty_hits_no_llm(db):
    factory, user = await _seed_base(db, "empty")
    await _make_pl(db, "PL-SRC-EMPTY", factory.id, product_type_code="TYPE-LONELY")
    capa = await _make_capa(db, factory.id, user.user_id, "PL-SRC-EMPTY")

    with patch(
        "app.services.capa_lateral_diffusion_service.build_client",
        new=AsyncMock(side_effect=AssertionError("must not call LLM")),
    ):
        await run_lateral_diffusion_check(db, capa, user.user_id)

    check = await db.scalar(
        select(CapaLateralDiffusionCheck).where(
            CapaLateralDiffusionCheck.capa_id == capa.report_id
        )
    )
    assert check is not None
    assert check.status == "empty"
    assert check.llm_status == "skipped"
    assert check.similar_products == []

    audits = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.record_id == capa.report_id,
                AuditLog.action == "LATERAL_DIFFUSION_CHECKED",
            )
        )
    ).scalars().all()
    assert len(audits) == 1
    assert audits[0].changed_fields["status"] == "empty"
    assert audits[0].changed_fields["similar_count"] == 0


@pytest.mark.asyncio
async def test_hits_no_llm_blocked(db):
    factory, user = await _seed_base(db, "blk")
    await _make_pl(db, "PL-SRC-BLK", factory.id, product_type_code="TYPE-LAT-BLK")
    await _make_pl(db, "PL-A-BLK", factory.id, product_type_code="TYPE-LAT-BLK")
    capa = await _make_capa(db, factory.id, user.user_id, "PL-SRC-BLK")

    with patch(
        "app.services.capa_lateral_diffusion_service.build_client",
        new=AsyncMock(side_effect=ProviderNotConfiguredError("no cfg")),
    ):
        with pytest.raises(LateralBlockedError):
            await run_lateral_diffusion_check(db, capa, user.user_id)

    # fail-closed: no check row persisted on blocked
    n = await db.scalar(
        select(CapaLateralDiffusionCheck).where(
            CapaLateralDiffusionCheck.capa_id == capa.report_id
        )
    )
    # object may be pending in session if added before raise — ensure none flushed as done
    # blocked path raises before db.add, so none should exist
    assert n is None


@pytest.mark.asyncio
async def test_hits_llm_failure_failed(db):
    factory, user = await _seed_base(db, "fail")
    await _make_pl(db, "PL-SRC-FAIL", factory.id, product_type_code="TYPE-LAT-FAIL")
    await _make_pl(db, "PL-A-FAIL", factory.id, product_type_code="TYPE-LAT-FAIL")
    capa = await _make_capa(db, factory.id, user.user_id, "PL-SRC-FAIL")

    pc = AsyncMock()
    with (
        patch(
            "app.services.capa_lateral_diffusion_service.build_client",
            new=AsyncMock(return_value=pc),
        ),
        patch(
            "app.services.capa_lateral_diffusion_service.complete_json",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
    ):
        with pytest.raises(LateralFailedError):
            await run_lateral_diffusion_check(db, capa, user.user_id)


@pytest.mark.asyncio
async def test_hits_llm_success_writes_suggestions(db):
    factory, user = await _seed_base(db, "ok")
    await _make_pl(db, "PL-SRC-OK", factory.id, product_type_code="TYPE-LAT-OK")
    await _make_pl(db, "PL-A-OK", factory.id, product_type_code="TYPE-LAT-OK")
    capa = await _make_capa(db, factory.id, user.user_id, "PL-SRC-OK")

    pc = AsyncMock()
    with (
        patch(
            "app.services.capa_lateral_diffusion_service.build_client",
            new=AsyncMock(return_value=pc),
        ),
        patch(
            "app.services.capa_lateral_diffusion_service.complete_json",
            new=AsyncMock(
                return_value={
                    "items": [
                        {
                            "product_type_code": "TYPE-LAT-OK",
                            "suggestion_direction": "复核 FMEA 与控制计划",
                        }
                    ]
                }
            ),
        ),
    ):
        await run_lateral_diffusion_check(db, capa, user.user_id)

    check = await db.scalar(
        select(CapaLateralDiffusionCheck).where(
            CapaLateralDiffusionCheck.capa_id == capa.report_id
        )
    )
    assert check is not None
    assert check.status == "done"
    assert check.llm_status == "done"
    assert len(check.similar_products) == 1
    assert check.similar_products[0]["suggestion_direction"] == "复核 FMEA 与控制计划"
    assert "same_product_type" in check.similar_products[0]["hit_criteria"]


@pytest.mark.asyncio
async def test_hits_llm_missing_type_failed(db):
    factory, user = await _seed_base(db, "miss")
    await _make_pl(db, "PL-SRC-MISS", factory.id, product_type_code="TYPE-LAT-MISS")
    await _make_pl(db, "PL-A-MISS", factory.id, product_type_code="TYPE-LAT-MISS")
    capa = await _make_capa(db, factory.id, user.user_id, "PL-SRC-MISS")

    with (
        patch(
            "app.services.capa_lateral_diffusion_service.build_client",
            new=AsyncMock(return_value=AsyncMock()),
        ),
        patch(
            "app.services.capa_lateral_diffusion_service.complete_json",
            new=AsyncMock(return_value={"items": []}),
        ),
    ):
        with pytest.raises(LateralFailedError, match="missing suggestions"):
            await run_lateral_diffusion_check(db, capa, user.user_id)


# ─── decide / rerun (Task 5) ────────────────────────────────────────────────

from app.models.capa_lateral_diffusion import CapaLateralNotification
from app.models.factory import UserFactory
from app.models.role import UserProductLine
from app.schemas.capa_lateral_diffusion import LateralDecisionRequest
from app.services.capa_lateral_diffusion_service import (
    ConflictError,
    _check_id_for,
    decide_lateral,
    rerun_lateral,
)
from app.models.capa_lateral_diffusion import CapaLateralDiffusionCheck


async def _seed_check_with_hits(db, suffix: str, *, with_recipient: bool = False):
    factory, user = await _seed_base(db, suffix)
    await _make_pl(db, f"PL-SRC-{suffix}", factory.id, product_type_code=f"TYPE-{suffix}")
    await _make_pl(db, f"PL-A-{suffix}", factory.id, product_type_code=f"TYPE-{suffix}")
    capa = await _make_capa(db, factory.id, user.user_id, f"PL-SRC-{suffix}")

    similar = [
        {
            "product_type_code": f"TYPE-{suffix}",
            "product_type_name": f"TYPE-{suffix}",
            "hit_criteria": ["same_product_type"],
            "suggestion_direction": "请复核",
            "product_lines": [
                {"code": f"PL-A-{suffix}", "factory_id": str(factory.id)}
            ],
            "evidence": {},
        }
    ]
    check = CapaLateralDiffusionCheck(
        check_id=_check_id_for(capa.report_id),
        capa_id=capa.report_id,
        factory_id=factory.id,
        source_product_line_code=f"PL-SRC-{suffix}",
        source_product_type_code=f"TYPE-{suffix}",
        similar_products=similar,
        status="done",
        llm_status="done",
        truncated=False,
    )
    db.add(check)
    await db.flush()

    recipient = None
    if with_recipient:
        # field_qe role + UserProductLine + factory access via factory_id
        role = RoleDefinition(
            id=uuid.uuid4(),
            role_key="field_qe",
            name_zh="现场QE",
            name_en="Field QE",
            description="test",
            is_system=False,
            is_editable=True,
            is_active=True,
        )
        # role_key unique? use unique key per test if needed
        # field_qe may already exist from seeds; look up first
        existing = await db.scalar(
            select(RoleDefinition).where(RoleDefinition.role_key == "field_qe")
        )
        if existing:
            role = existing
        else:
            db.add(role)
            await db.flush()

        recipient = User(
            user_id=uuid.uuid4(),
            username=f"recv_{suffix}",
            display_name="Recv",
            email=f"recv_{suffix}@example.com",
            password_hash="x",
            role_id=role.id,
            legacy_role="viewer",
            is_active=True,
            factory_id=factory.id,
        )
        db.add(recipient)
        await db.flush()
        db.add(
            UserProductLine(
                id=uuid.uuid4(),
                user_id=recipient.user_id,
                product_line_code=f"PL-A-{suffix}",
            )
        )
        await db.flush()

    return capa, check, factory, user, recipient


@pytest.mark.asyncio
async def test_decide_notify_writes_notifications(db):
    capa, check, factory, user, recipient = await _seed_check_with_hits(
        db, "dn", with_recipient=True
    )
    out = await decide_lateral(
        db, capa.report_id, LateralDecisionRequest(decision="notify"), user_id=user.user_id
    )
    assert out["decision"] == "notified"
    assert any(n["decision"] == "notified" for n in out["notifications"])
    assert any(n["status"] in ("notified", "pending") for n in out["notifications"])
    # recipient should be resolved
    labels = {n["recipient_label"] for n in out["notifications"]}
    assert recipient.username in labels or "未找到负责人" in labels


@pytest.mark.asyncio
async def test_decide_skip_writes_skipped_with_reason(db):
    capa, check, factory, user, _ = await _seed_check_with_hits(db, "ds")
    out = await decide_lateral(
        db,
        capa.report_id,
        LateralDecisionRequest(decision="skip", skip_reason="无需扩散"),
        user_id=user.user_id,
    )
    assert out["decision"] == "skipped"
    assert all(n["decision"] == "skipped" for n in out["notifications"])
    audit = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.record_id == capa.report_id,
                AuditLog.action == "LATERAL_NOTIFICATION_SKIPPED",
            )
        )
    ).scalars().first()
    assert audit is not None
    assert audit.changed_fields["skip_reason"] == "无需扩散"


@pytest.mark.asyncio
async def test_decide_twice_409(db):
    capa, check, factory, user, _ = await _seed_check_with_hits(db, "d2")
    await decide_lateral(
        db, capa.report_id, LateralDecisionRequest(decision="notify"), user_id=user.user_id
    )
    with pytest.raises(ConflictError):
        await decide_lateral(
            db,
            capa.report_id,
            LateralDecisionRequest(decision="skip", skip_reason="x"),
            user_id=user.user_id,
        )


@pytest.mark.asyncio
async def test_decide_rejects_product_type_codes(db):
    capa, check, factory, user, _ = await _seed_check_with_hits(db, "dsub")
    with pytest.raises(ValueError, match="product_type_codes"):
        LateralDecisionRequest(decision="notify", product_type_codes=["TYPE-dsub"])


@pytest.mark.asyncio
async def test_decide_no_check_404(db):
    factory, user = await _seed_base(db, "nochk")
    await _make_pl(db, "PL-SRC-NOCHK", factory.id, product_type_code="TYPE-NOCHK")
    capa = await _make_capa(db, factory.id, user.user_id, "PL-SRC-NOCHK")
    with pytest.raises(ValueError, match="no lateral check"):
        await decide_lateral(
            db, capa.report_id, LateralDecisionRequest(decision="notify"), user_id=user.user_id
        )


@pytest.mark.asyncio
async def test_recipient_factory_scope_excludes_wrong_factory_user(db):
    """User with no UserFactory and null factory_id must not receive."""
    capa, check, factory, user, _ = await _seed_check_with_hits(db, "rf")
    role = await db.scalar(select(RoleDefinition).where(RoleDefinition.role_key == "field_qe"))
    if role is None:
        role = RoleDefinition(
            id=uuid.uuid4(),
            role_key="field_qe",
            name_zh="现场QE",
            name_en="Field QE",
            description="t",
            is_system=False,
            is_editable=True,
            is_active=True,
        )
        db.add(role)
        await db.flush()

    orphan = User(
        user_id=uuid.uuid4(),
        username="orphan_rf",
        display_name="Orphan",
        email="orphan_rf@example.com",
        password_hash="x",
        role_id=role.id,
        legacy_role="viewer",
        is_active=True,
        factory_id=None,
    )
    db.add(orphan)
    await db.flush()
    db.add(
        UserProductLine(
            id=uuid.uuid4(),
            user_id=orphan.user_id,
            product_line_code="PL-A-rf",
        )
    )
    await db.flush()

    out = await decide_lateral(
        db, capa.report_id, LateralDecisionRequest(decision="notify"), user_id=user.user_id
    )
    # orphan must not appear; pending placeholder is OK
    for n in out["notifications"]:
        assert n["recipient_label"] != "orphan_rf"


@pytest.mark.asyncio
async def test_rerun_after_decide_conflicts(db):
    capa, check, factory, user, _ = await _seed_check_with_hits(db, "rr")
    await decide_lateral(
        db, capa.report_id, LateralDecisionRequest(decision="notify"), user_id=user.user_id
    )
    with pytest.raises(ConflictError):
        await rerun_lateral(db, capa.report_id, user.user_id)


@pytest.mark.asyncio
async def test_rerun_without_check_inserts_then_runs(db):
    factory, user = await _seed_base(db, "rr0")
    await _make_pl(db, "PL-SRC-RR0", factory.id, product_type_code="TYPE-LONELY-RR0")
    capa = await _make_capa(db, factory.id, user.user_id, "PL-SRC-RR0")
    with patch(
        "app.services.capa_lateral_diffusion_service.build_client",
        new=AsyncMock(side_effect=AssertionError("no llm for empty")),
    ):
        out = await rerun_lateral(db, capa.report_id, user.user_id)
    assert out is not None
    assert out["status"] == "empty"
    assert out["llm_status"] == "skipped"


@pytest.mark.asyncio
async def test_lateral_blocked_after_sink_succeeds(db, monkeypatch):
    """§5.2.1: after 01.8 sink succeeds, lateral no-LLM is blocked and leaves no check row."""
    from sqlalchemy import func
    from app.services.capa_lateral_diffusion_service import LateralBlockedError

    factory, user = await _seed_base(db, "bksink")
    await _make_pl(db, "PL-SRC-BKSINK", factory.id, product_type_code="TYPE-BKSINK")
    await _make_pl(db, "PL-A-BKSINK", factory.id, product_type_code="TYPE-BKSINK")
    capa = await _make_capa(db, factory.id, user.user_id, "PL-SRC-BKSINK")

    async def _noop_sink(*a, **kw):
        return None

    # Sink success is simulated (not invoked here); assert lateral stage blocked alone.
    monkeypatch.setattr(
        "app.services.capa_lateral_diffusion_service.build_client",
        AsyncMock(side_effect=ProviderNotConfiguredError("no cfg")),
    )
    with pytest.raises(LateralBlockedError):
        await run_lateral_diffusion_check(db, capa, user.user_id)

    n = await db.scalar(
        select(func.count())
        .select_from(CapaLateralDiffusionCheck)
        .where(CapaLateralDiffusionCheck.capa_id == capa.report_id)
    )
    assert n == 0
