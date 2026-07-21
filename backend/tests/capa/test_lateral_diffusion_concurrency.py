"""Concurrency tests for lateral diffusion decide/rerun (US-E2E-01.9 Task 6).

Uses true multi-session asyncio.gather via the sessionmaker fixture (real
commits, NullPool) so FOR UPDATE + partial unique indexes are exercised.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import func, select
from unittest.mock import AsyncMock, patch

from app.models.capa import CAPAEightD
from app.models.capa_lateral_diffusion import (
    CapaLateralDiffusionCheck,
    CapaLateralNotification,
)
from app.models.factory import Factory
from app.models.product_line import ProductLine
from app.models.product_type import ProductType
from app.models.role import RoleDefinition
from app.models.user import User
from app.schemas.capa_lateral_diffusion import LateralDecisionRequest
from app.services.capa_lateral_diffusion_service import (
    ConflictError,
    _check_id_for,
    decide_lateral,
    rerun_lateral,
)

pytestmark = pytest.mark.requires_db


async def _seed_closed_capa_with_check(
    sessionmaker, suffix: str, *, with_check: bool = True, lonely: bool = False
):
    """Persist factory/user/capa(+check) with real commits for multi-session tests.

    lonely=True: only source PL (no same-type peer) so rerun yields empty hits / no LLM.
    """
    factory_id = uuid.uuid4()
    user_id = uuid.uuid4()
    capa_id = uuid.uuid4()
    role_id = uuid.uuid4()
    type_code = f"T{suffix}"[:20]
    pl_src = f"PS{suffix}"[:20]
    pl_a = f"PA{suffix}"[:20]

    async with sessionmaker() as s:
        s.add(Factory(id=factory_id, code=f"F{suffix}"[:20], name=f"Fac {suffix}", is_active=True))
        await s.flush()
        existing_pt = await s.scalar(select(ProductType).where(ProductType.code == type_code))
        if not existing_pt:
            s.add(ProductType(code=type_code, name=type_code, is_active=True))
            await s.flush()
        s.add(ProductLine(code=pl_src, name=pl_src, factory_id=factory_id, product_type_code=type_code))
        if not lonely:
            s.add(ProductLine(code=pl_a, name=pl_a, factory_id=factory_id, product_type_code=type_code))
        s.add(
            RoleDefinition(
                id=role_id,
                role_key=f"r{suffix}"[:40],
                name_zh="t",
                name_en="t",
                is_system=False,
                is_editable=True,
                is_active=True,
            )
        )
        await s.flush()
        s.add(
            User(
                user_id=user_id,
                username=f"u{suffix}"[:40],
                display_name="u",
                password_hash="x",
                role_id=role_id,
                legacy_role="viewer",
                is_active=True,
                factory_id=factory_id,
            )
        )
        await s.flush()
        s.add(
            CAPAEightD(
                report_id=capa_id,
                document_no=f"8D-{suffix}"[:50],
                title="lat concurrent",
                product_line_code=pl_src,
                factory_id=factory_id,
                status="D8_CLOSURE",
                severity="general",
                created_by=user_id,
                d1_team=[],
            )
        )
        await s.flush()
        if with_check:
            s.add(
                CapaLateralDiffusionCheck(
                    check_id=_check_id_for(capa_id),
                    capa_id=capa_id,
                    factory_id=factory_id,
                    source_product_line_code=pl_src,
                    source_product_type_code=type_code,
                    similar_products=[
                        {
                            "product_type_code": type_code,
                            "hit_criteria": ["same_product_type"],
                            "suggestion_direction": "x",
                            "product_lines": [
                                {"code": pl_a, "factory_id": str(factory_id)}
                            ],
                            "evidence": {},
                        }
                    ],
                    status="done",
                    llm_status="done",
                    truncated=False,
                )
            )
        await s.commit()

    return capa_id, user_id, factory_id


@pytest.mark.asyncio
async def test_notify_vs_skip_only_one_wins(sessionmaker):
    capa_id, user_id, _ = await _seed_closed_capa_with_check(sessionmaker, uuid.uuid4().hex[:8])

    async def run(decision, **kw):
        async with sessionmaker() as db:
            try:
                out = await decide_lateral(
                    db,
                    capa_id,
                    LateralDecisionRequest(decision=decision, **kw),
                    user_id=user_id,
                )
                await db.commit()
                return out
            except Exception:
                await db.rollback()
                raise

    res = await asyncio.wait_for(
        asyncio.gather(
            run("notify"),
            run("skip", skip_reason="x"),
            return_exceptions=True,
        ),
        timeout=30.0,
    )
    wins = [r for r in res if not isinstance(r, Exception)]
    conflicts = [r for r in res if isinstance(r, ConflictError)]
    assert len(wins) == 1, res
    assert len(conflicts) == 1, res

    async with sessionmaker() as db:
        rows = (
            await db.execute(
                select(CapaLateralNotification).where(
                    CapaLateralNotification.capa_id == capa_id
                )
            )
        ).scalars().all()
        decisions = {r.decision for r in rows}
        assert decisions != {"notified", "skipped"}
        assert decisions in ({"notified"}, {"skipped"})


@pytest.mark.asyncio
async def test_decide_vs_rerun_consistent(sessionmaker):
    capa_id, user_id, _ = await _seed_closed_capa_with_check(sessionmaker, uuid.uuid4().hex[:8])

    async def decide():
        async with sessionmaker() as db:
            try:
                out = await decide_lateral(
                    db,
                    capa_id,
                    LateralDecisionRequest(decision="notify"),
                    user_id=user_id,
                )
                await db.commit()
                return out
            except Exception:
                await db.rollback()
                raise

    async def rerun():
        async with sessionmaker() as db:
            try:
                # If rerun wins the race (before decide), matching needs no LLM
                # only if empty; with hits mock a successful LLM so path is clean.
                with (
                    patch(
                        "app.services.capa_lateral_diffusion_service.build_client",
                        new=AsyncMock(return_value=AsyncMock()),
                    ),
                    patch(
                        "app.services.capa_lateral_diffusion_service.complete_json",
                        new=AsyncMock(
                            return_value={
                                "items": [
                                    {
                                        "product_type_code": "placeholder",
                                        "suggestion_direction": "x",
                                    }
                                ]
                            }
                        ),
                    ),
                ):
                    # complete_json items must cover whatever types match finds —
                    # use a side_effect that mirrors input similar set.
                    async def _cj(pc, prompt, schema):
                        # Extract TYPE codes from prompt is brittle; return
                        # generous pass-through via re-query isn't available.
                        # Instead, re-run with lonely empty fixture? Keep simple:
                        return {
                            "items": [
                                {
                                    "product_type_code": t,
                                    "suggestion_direction": "x",
                                }
                                for t in _extract_types_from_prompt(prompt)
                            ]
                        }

                    with patch(
                        "app.services.capa_lateral_diffusion_service.complete_json",
                        new=AsyncMock(side_effect=_cj),
                    ):
                        out = await rerun_lateral(db, capa_id, user_id=user_id)
                await db.commit()
                return out
            except Exception:
                await db.rollback()
                raise

    def _extract_types_from_prompt(prompt: str) -> list[str]:
        import re
        return re.findall(r'"product_type_code": "([^"]+)"', prompt)

    res = await asyncio.wait_for(
        asyncio.gather(decide(), rerun(), return_exceptions=True),
        timeout=30.0,
    )
    # Serialize via CAPA FOR UPDATE: either ConflictError, or both succeed without
    # dual-decision dirty write (rerun-first then decide is legal).
    hard = [
        r
        for r in res
        if isinstance(r, Exception) and not isinstance(r, ConflictError)
    ]
    assert not hard, res

    async with sessionmaker() as db:
        rows = (
            await db.execute(
                select(CapaLateralNotification).where(
                    CapaLateralNotification.capa_id == capa_id
                )
            )
        ).scalars().all()
        if rows:
            assert {r.decision for r in rows} != {"notified", "skipped"}
            assert {r.decision for r in rows} in ({"notified"}, {"skipped"})


@pytest.mark.asyncio
async def test_dual_rerun_without_check_no_500(sessionmaker):
    capa_id, user_id, _ = await _seed_closed_capa_with_check(
        sessionmaker, uuid.uuid4().hex[:8], with_check=False, lonely=True
    )

    async def rerun():
        async with sessionmaker() as db:
            try:
                with patch(
                    "app.services.capa_lateral_diffusion_service.build_client",
                    new=AsyncMock(side_effect=AssertionError("empty should skip llm")),
                ):
                    out = await rerun_lateral(db, capa_id, user_id=user_id)
                await db.commit()
                return out
            except Exception:
                await db.rollback()
                raise

    res = await asyncio.wait_for(
        asyncio.gather(rerun(), rerun(), return_exceptions=True),
        timeout=30.0,
    )
    hard_errors = [
        r
        for r in res
        if isinstance(r, Exception) and not isinstance(r, ConflictError)
    ]
    assert not hard_errors, res

    async with sessionmaker() as db:
        n = await db.scalar(
            select(func.count())
            .select_from(CapaLateralDiffusionCheck)
            .where(CapaLateralDiffusionCheck.capa_id == capa_id)
        )
        assert n == 1
