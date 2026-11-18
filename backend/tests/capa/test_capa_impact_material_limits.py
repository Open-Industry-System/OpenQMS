"""A projection cap must not reveal undisclosed measures or inherited sources."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.schemas.pfmea_impact import MeasureKey
from app.services import capa_impact_material as impact


@pytest.mark.asyncio
async def test_unfiltered_measure_count_uses_generic_denial_on_overflow(monkeypatch):
    monkeypatch.setattr(impact, "_MAX_MEASURES", 1)
    # The bounded initial query has no per-measure ACL yet. The rows must
    # neither be counted for the user nor inspected as authorized measures.
    db = SimpleNamespace(execute=AsyncMock(return_value=Mock(all=Mock(return_value=[None, None]))))
    with pytest.raises(impact.ImpactMaterialUnavailable, match="^CAPA impact material unavailable$"):
        await impact._measure_keys(db, uuid4(), uuid4(), uuid4(), None)


@pytest.mark.asyncio
async def test_source_overflow_before_final_receipt_authority_uses_generic_denial(monkeypatch):
    monkeypatch.setattr(impact, "_MAX_SOURCES", 1)
    report_id = uuid4()
    scope = SimpleNamespace(user=SimpleNamespace(user_id=uuid4()))
    target = SimpleNamespace(factory_id=uuid4(), product_line_code="A", status="D5_CORRECTION")
    tenant = SimpleNamespace(tenant_id=uuid4(), generation=1)
    db = SimpleNamespace(info={"tenant_binding": tenant},
        execute=AsyncMock(return_value=Mock(one_or_none=Mock(return_value=SimpleNamespace(is_verified=True)))))
    revision = SimpleNamespace(revision_id=uuid4())
    proof = SimpleNamespace(proof_id=uuid4(), verification_id=uuid4(),
        factory_id=target.factory_id, product_line_code=target.product_line_code)
    proposals = [SimpleNamespace(proposal_id=uuid4(), state="adopted") for _ in range(2)]
    formal = {MeasureKey(measure_id=uuid4(), formal_revision=None): row for row in proposals}
    for module, name, value in (
        (impact.capa_d4_material, "require_current_egress_statement", None),
        (impact, "current_capa_access", (None, None, None)),
        (impact, "current_capa_target_metadata", target),
        (impact.capa_d4_material, "authorize_root", (revision, ())),
        (impact, "require_ordinary_capture_material", None),
        (impact, "_proof_and_revision", (proof, revision)),
        (impact, "authorize_verifications", ["present"]),
        (impact, "_revision_sources", {}),
        (impact, "_measure_keys", formal),
        (impact.capa_d5_measures, "_visible_metadata",
            (target, proposals, {row.proposal_id: [] for row in proposals})),
        (impact.capa_d4_material, "require_root_freshness", (revision, ())),
    ):
        monkeypatch.setattr(module, name, AsyncMock(return_value=value))
    # The first receipt can overflow the cap before the second receipt's
    # signed source epochs have been checked. No reason may expose that count.
    receipts = AsyncMock(side_effect=[{uuid4(): None, uuid4(): None}, impact.ImpactMaterialUnavailable()])
    monkeypatch.setattr(impact, "_measure_sources", receipts)
    with pytest.raises(impact.ImpactMaterialUnavailable, match="^CAPA impact material unavailable$"):
        await impact._metadata(db, scope, report_id)
    receipts.assert_awaited_once()
