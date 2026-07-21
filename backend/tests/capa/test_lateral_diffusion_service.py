from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
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
