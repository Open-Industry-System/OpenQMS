"""E2E seed D3 fixture reset regression tests.

These tests verify:
- D3 chain reset refuses to run outside E2E mode.
- Consecutive seed calls restore initial fixture state without accumulation.
"""
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, update

from app.config import settings
from app.models.capa import CAPAEightD
from app.models.capa_d3 import CapaD3Execution, CapaD3ImpactReport, CapaD3ImportRun
from app.seed_e2e import (
    _reset_d3_chain,
    _seed_accounts,
    _seed_d3_test_capas,
    _seed_factories,
    _seed_product_line,
)
from app.seed_e2e_constants import D3_E2E_CAPA_DOC_NO_REPORTED
from app.services.agent import provider_adapter


@pytest.fixture
async def d3_seed_base(db):
    """Seed factories, product lines and accounts required by D3 fixtures."""
    factory_ids = await _seed_factories(db)
    await _seed_product_line(db, factory_ids)
    await _seed_accounts(db, factory_ids)
    await db.commit()
    return factory_ids


@pytest.fixture
def d3_seed_llm(monkeypatch):
    """Mock LLM provider so D3 report/advice generation succeeds without credentials."""

    async def build_client(_db):
        return SimpleNamespace(model="e2e-mock")

    async def complete_json(_client, _prompt, response_schema):
        props = response_schema.get("properties", {})
        if "risk_level" in props:
            return {"risk_level": "high", "risk_explanation": "E2E risk"}
        return {
            "advice": [
                {
                    "advice_type": "alternative",
                    "advice_text": "E2E action",
                    "target_batch_refs": None,
                    "provenance_sources_hint": [],
                }
            ]
        }

    monkeypatch.setattr(provider_adapter, "build_client", build_client)
    monkeypatch.setattr(provider_adapter, "complete_json", complete_json)


async def test_d3_reset_refuses_non_e2e_mode(db, monkeypatch):
    """_reset_d3_chain must fail-closed when E2E_MODE is disabled."""
    monkeypatch.setattr(settings, "E2E_MODE", False)
    with pytest.raises(RuntimeError, match="requires E2E_MODE"):
        await _reset_d3_chain(db, D3_E2E_CAPA_DOC_NO_REPORTED, None)


async def test_d3_seed_twice_restores_initial_state_without_accumulation(
    db, monkeypatch, d3_seed_base, d3_seed_llm,
):
    """Two consecutive seed calls recover a mutated CAPA to its initial state."""
    monkeypatch.setattr(settings, "E2E_MODE", True)
    monkeypatch.setattr(settings, "TENANT_MODE", "single")

    await _seed_d3_test_capas(db)

    capa = await db.scalar(select(CAPAEightD).where(
        CAPAEightD.document_no == D3_E2E_CAPA_DOC_NO_REPORTED))
    report = await db.scalar(select(CapaD3ImpactReport).join(
        CapaD3ImportRun, CapaD3ImpactReport.run_id == CapaD3ImportRun.run_id).where(
        CapaD3ImportRun.capa_id == capa.report_id,
        CapaD3ImpactReport.is_current.is_(True)))

    # Simulate a test that advanced the CAPA and left execution data behind.
    db.add(CapaD3Execution(
        report_id=report.report_id,
        generation_id=None,
        advice_id=None,
        factory_id=capa.factory_id,
        source="manual",
        measure_text="mutated",
        result_status="in_progress",
        evidence_refs=[],
        executed_by=capa.created_by,
    ))
    await db.execute(update(CAPAEightD).where(
        CAPAEightD.report_id == capa.report_id).values(status="D4_ROOT_CAUSE"))
    await db.commit()

    # Re-seed: should reset the D3 chain and restore the initial status.
    await _seed_d3_test_capas(db)
    await db.refresh(capa)

    assert capa.status == "D3_INTERIM"
    assert await db.scalar(select(func.count()).select_from(CapaD3Execution).join(
        CapaD3ImpactReport, CapaD3Execution.report_id == CapaD3ImpactReport.report_id).join(
        CapaD3ImportRun, CapaD3ImpactReport.run_id == CapaD3ImportRun.run_id).where(
        CapaD3ImportRun.capa_id == capa.report_id)) == 0
    assert await db.scalar(select(func.count()).select_from(CapaD3ImportRun).where(
        CapaD3ImportRun.capa_id == capa.report_id)) == 1
    assert await db.scalar(select(func.count()).select_from(CapaD3ImpactReport).join(
        CapaD3ImportRun, CapaD3ImpactReport.run_id == CapaD3ImportRun.run_id).where(
        CapaD3ImportRun.capa_id == capa.report_id,
        CapaD3ImpactReport.is_current.is_(True))) == 1
