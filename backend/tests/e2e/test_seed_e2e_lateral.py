"""US-E2E-01.9 lateral diffusion seed guards."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.config import settings
from app.models.capa import CAPAEightD
from app.models.product_line import ProductLine
from app.seed_e2e import (
    _seed_accounts,
    _seed_factories,
    _seed_lateral_diffusion,
    _seed_product_line,
)
from app.seed_e2e_constants import (
    LATERAL_E2E_CAPA_001,
    LATERAL_E2E_CAPA_002,
    LATERAL_E2E_CAPA_BLOCK,
    LATERAL_E2E_CAPA_EMPTY,
    LATERAL_PL_SRC,
)


@pytest.mark.asyncio
async def test_lateral_seed_present(db, monkeypatch):
    monkeypatch.setattr(settings, "E2E_MODE", True)
    monkeypatch.setattr(settings, "TENANT_MODE", "single")
    factory_ids = await _seed_factories(db)
    await _seed_product_line(db, factory_ids)
    await _seed_accounts(db, factory_ids)
    await _seed_lateral_diffusion(db, factory_ids)
    await db.flush()

    for doc in (
        LATERAL_E2E_CAPA_001,
        LATERAL_E2E_CAPA_002,
        LATERAL_E2E_CAPA_BLOCK,
        LATERAL_E2E_CAPA_EMPTY,
    ):
        capa = await db.scalar(select(CAPAEightD).where(CAPAEightD.document_no == doc))
        assert capa is not None, doc

    pl = await db.scalar(select(ProductLine).where(ProductLine.code == LATERAL_PL_SRC))
    assert pl is not None
