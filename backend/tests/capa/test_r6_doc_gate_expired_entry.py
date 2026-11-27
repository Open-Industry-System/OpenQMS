"""Persisted expired inputs retain metadata-first doc-gate admission."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import inspect

from app.models.capa import CAPAEightD
from app.services import capa_doc_gate_service as gate
from tests.capa.test_r6_manual_doc_gate import (
    local_case, correction_case, staff_case, d5_case, committed_runtime, enter_doc_gate,
)

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
async def test_expired_restricted_report_denies_before_provider_or_body_refetch(local_case, monkeypatch):
    c = local_case
    await enter_doc_gate(c)
    async with c.factory(binding=c.binding) as db:
        capa = await db.get(CAPAEightD, c.report.report_id)
        db.sync_session.expire_on_commit = True
        await db.commit()
        assert 'report_id' in inspect(capa).expired_attributes
        refresh = AsyncMock(side_effect=AssertionError('body refetch before restricted admission'))
        provider = AsyncMock(side_effect=AssertionError('provider before restricted admission'))
        monkeypatch.setattr(gate, '_fresh_capa_phase', refresh)
        monkeypatch.setattr(gate.provider_adapter, 'build_client', provider)
        with pytest.raises(PermissionError, match='Restricted report requires manual analysis'):
            await gate.generate_impact_analysis(db, capa, c.scope.user.user_id)
        refresh.assert_not_awaited()
        provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_unpersisted_report_rejects_before_source_or_provider(monkeypatch):
    from app.services import capa_r6_local_closure
    capa = CAPAEightD(report_id=uuid4(), document_no='UNPERSISTED', title='Synthetic')
    assert inspect(capa).identity is None
    eligible = AsyncMock(side_effect=AssertionError('source lookup for unpersisted input'))
    provider = AsyncMock(side_effect=AssertionError('provider for unpersisted input'))
    monkeypatch.setattr(capa_r6_local_closure, 'eligible', eligible)
    monkeypatch.setattr(gate.provider_adapter, 'build_client', provider)
    with pytest.raises(ValueError, match='^CAPA input is not persisted$'):
        await gate.generate_impact_analysis(SimpleNamespace(), capa, uuid4())
    eligible.assert_not_awaited()
    provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_restricted_phase2_denies_before_body_refetch_or_provider(local_case, monkeypatch):
    c = local_case
    await enter_doc_gate(c)
    async with c.factory(binding=c.binding) as db:
        capa = await db.get(CAPAEightD, c.report.report_id)
        db.sync_session.expire_on_commit = True
        await db.commit()
        assert 'report_id' in inspect(capa).expired_attributes
        refresh = AsyncMock(side_effect=AssertionError('phase2 body refetch before source binding'))
        provider = AsyncMock(side_effect=AssertionError('phase2 provider before source binding'))
        monkeypatch.setattr(gate, '_fresh_capa_phase', refresh)
        monkeypatch.setattr(gate.provider_adapter, 'complete_json', provider)
        with pytest.raises(PermissionError, match='^D4_FULL_MATERIAL_UNAVAILABLE'):
            await gate._phase2_llm(db, capa, {'actor_id': c.scope.user.user_id})
        refresh.assert_not_awaited()
        provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_unpersisted_phase2_rejects_before_binding_or_provider(monkeypatch):
    from app.services import capa_d4_material
    capa = CAPAEightD(report_id=uuid4(), document_no='UNPERSISTED-PHASE2', title='Synthetic')
    binding = AsyncMock(side_effect=AssertionError('binding lookup for unpersisted input'))
    provider = AsyncMock(side_effect=AssertionError('provider for unpersisted phase2 input'))
    monkeypatch.setattr(capa_d4_material, 'legacy_capa_read_binding', binding)
    monkeypatch.setattr(gate.provider_adapter, 'complete_json', provider)
    with pytest.raises(ValueError, match='^CAPA input is not persisted$'):
        await gate._phase2_llm(SimpleNamespace(), capa, {'actor_id': uuid4()})
    binding.assert_not_awaited()
    provider.assert_not_awaited()
