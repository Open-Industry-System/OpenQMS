"""D3→D4 fail-closed gate tests (US-E2E-01.1 Task 5)."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text, update

from app.models.capa_d3 import (
    CapaD3AiAdvice,
    CapaD3AdviceGeneration,
    CapaD3ContainmentSnapshot,
    CapaD3Execution,
    CapaD3ImpactReport,
    CapaD3ImportRun,
)
from app.models.factory import Factory
from app.schemas.capa import AdvanceRequest
from app.services.capa_d3_containment_service import _current_advice_generation
from app.services.capa_service import advance_capa


# ===== Helpers =====


async def _current_report_for_run(db, run_id):
    return await db.scalar(
        select(CapaD3ImpactReport).where(
            CapaD3ImpactReport.run_id == run_id,
            CapaD3ImpactReport.is_current == True,
        )
    )


async def _insert_advice_generation(db, report_id, factory_id, user_id, is_current=True):
    """Insert a done advice_generation + one ai_advice for the generation."""
    gen = CapaD3AdviceGeneration(
        report_id=report_id,
        factory_id=factory_id,
        is_current=is_current,
        status="done",
        advice_count=1,
        rejected_advice_count=0,
        stage_runs=[],
        llm_available=True,
        generated_by=user_id,
        completed_at=datetime.utcnow(),
    )
    db.add(gen)
    await db.flush()
    await db.refresh(gen)

    advice = CapaD3AiAdvice(
        generation_id=gen.generation_id,
        factory_id=factory_id,
        advice_type="isolate",
        advice_text="test advice",
        source_provenance=[],
        target_batch_refs=[],
        stage_runs=[],
        llm_available=True,
        generated_by=user_id,
    )
    db.add(advice)
    await db.flush()
    await db.refresh(advice)

    return gen, advice


async def _insert_manual_execution(db, report_id, factory_id, user_id, result_status="completed"):
    exec_ = CapaD3Execution(
        report_id=report_id,
        factory_id=factory_id,
        source="manual",
        measure_text="manual containment",
        result_status=result_status,
        executed_by=user_id,
    )
    db.add(exec_)
    await db.flush()
    return exec_


async def _insert_adopted_execution(db, report_id, factory_id, generation_id, advice_id, user_id):
    exec_ = CapaD3Execution(
        report_id=report_id,
        factory_id=factory_id,
        generation_id=generation_id,
        advice_id=advice_id,
        source="adopted",
        measure_text="adopted containment",
        result_status="completed",
        executed_by=user_id,
    )
    db.add(exec_)
    await db.flush()
    return exec_


# ===== Fixtures =====


@pytest_asyncio.fixture
async def capa_d3_empty(capa_d3_setup):
    """CAPA in D3_INTERIM with no import run."""
    return capa_d3_setup


@pytest_asyncio.fixture
async def capa_d3_3types(db, capa_d3_imported):
    """Imported run missing the spc snapshot type."""
    capa, run, user = capa_d3_imported
    await db.execute(
        delete(CapaD3ContainmentSnapshot).where(
            CapaD3ContainmentSnapshot.run_id == run.run_id,
            CapaD3ContainmentSnapshot.snapshot_type == "spc",
        )
    )
    await db.flush()
    return capa, user


@pytest_asyncio.fixture
async def capa_d3_imported_no_done_report(db, capa_d3_imported):
    """Imported run with a failed/non-current impact report."""
    capa, run, user = capa_d3_imported
    report = await _current_report_for_run(db, run.run_id)
    if report:
        report.status = "failed"
        report.is_current = False
        report.completed_at = datetime.utcnow()
    await db.flush()
    return capa, user


@pytest_asyncio.fixture
async def capa_d3_imported_4types_done_report(capa_d3_imported):
    """Imported run with all 4 snapshot types and a done impact report."""
    capa, _run, user = capa_d3_imported
    return capa, user


@pytest_asyncio.fixture
async def capa_d3_with_manual_execution(db, capa_d3_imported):
    """Done report + one manual execution (completed)."""
    capa, run, user = capa_d3_imported
    report = await _current_report_for_run(db, run.run_id)
    await _insert_manual_execution(db, report.report_id, capa.factory_id, user.user_id)
    return capa, user


@pytest_asyncio.fixture
async def capa_d3_pure_manual_no_advice(db, capa_d3_imported):
    """Done report, no advice ever generated, one manual execution."""
    capa, run, user = capa_d3_imported
    report = await _current_report_for_run(db, run.run_id)
    current_gen = await _current_advice_generation(db, report.report_id)
    assert current_gen is None
    await _insert_manual_execution(db, report.report_id, capa.factory_id, user.user_id)
    return capa, user


@pytest_asyncio.fixture
async def capa_d3_regenerated_advice(db, capa_d3_imported):
    """Old-generation adopted execution exists, but a new generation is current."""
    capa, run, user = capa_d3_imported
    report = await _current_report_for_run(db, run.run_id)

    old_gen, old_advice = await _insert_advice_generation(
        db, report.report_id, capa.factory_id, user.user_id, is_current=True
    )
    await _insert_adopted_execution(
        db, report.report_id, capa.factory_id, old_gen.generation_id, old_advice.advice_id, user.user_id
    )

    # Demote old generation and create a new current one
    old_gen.is_current = False
    await db.flush()
    new_gen, _new_advice = await _insert_advice_generation(
        db, report.report_id, capa.factory_id, user.user_id, is_current=True
    )
    assert new_gen.generation_id != old_gen.generation_id
    return capa, user


@pytest_asyncio.fixture
async def capa_d3_manual_after_advice_regenerate(db, capa_d3_imported):
    """Manual execution exists alongside a fresh current advice generation."""
    capa, run, user = capa_d3_imported
    report = await _current_report_for_run(db, run.run_id)
    await _insert_manual_execution(db, report.report_id, capa.factory_id, user.user_id)
    await _insert_advice_generation(
        db, report.report_id, capa.factory_id, user.user_id, is_current=True
    )
    return capa, user


@pytest_asyncio.fixture
async def capa_d3_execution_demoted(db, capa_d3_imported):
    """Manual execution patched from completed to failed."""
    capa, run, user = capa_d3_imported
    report = await _current_report_for_run(db, run.run_id)
    exec_ = await _insert_manual_execution(db, report.report_id, capa.factory_id, user.user_id)
    exec_.result_status = "failed"
    await db.flush()
    return capa, user


@pytest_asyncio.fixture
async def capa_d3_failed_report(db, capa_d3_imported):
    """Current report status is failed."""
    capa, run, user = capa_d3_imported
    report = await _current_report_for_run(db, run.run_id)
    if report:
        report.status = "failed"
        report.is_current = False
        report.completed_at = datetime.utcnow()
    await db.flush()
    return capa, user


@pytest_asyncio.fixture
async def capa_d3_superseded_report(db, capa_d3_imported, superseded_run):
    """Current run's own report is not current (another run owns the current report)."""
    capa, run1, user = capa_d3_imported
    run2 = await db.scalar(
        select(CapaD3ImportRun).where(
            CapaD3ImportRun.capa_id == capa.report_id,
            CapaD3ImportRun.is_current == True,
        )
    )
    report1 = await _current_report_for_run(db, run1.run_id)
    if report1:
        report1.is_current = False
        await db.flush()

    # Demote run2 first to avoid transient violation of the partial unique index
    # on (capa_id) where is_current=true.
    if run2:
        run2.is_current = False
        await db.flush()
    run1.is_current = True
    await db.flush()
    return capa, user


@pytest_asyncio.fixture
async def capa_d3_cross_factory_run(db, capa_d3_imported):
    """Current run's factory_id differs from the CAPA's factory_id."""
    capa, run, user = capa_d3_imported
    other_factory = Factory(
        id=uuid.uuid4(),
        code="FAC-D3-OTHER",
        name="Other D3 Factory",
        is_active=True,
    )
    db.add(other_factory)
    await db.flush()

    # Defensive check: gate compares run.factory_id to capa.factory_id.
    # FKs normally enforce equality, so we bypass triggers for this defensive-only row update.
    await db.execute(text("SET LOCAL session_replication_role = replica;"))
    await db.execute(
        update(CapaD3ImportRun)
        .where(CapaD3ImportRun.run_id == run.run_id)
        .values(factory_id=other_factory.id)
    )
    await db.execute(text("SET LOCAL session_replication_role = origin;"))
    await db.flush()
    await db.refresh(run)
    await db.refresh(capa)
    return capa, user


# ===== Gate tests =====


async def test_gate_rejects_no_import(db, capa_d3_empty):
    capa, user = capa_d3_empty
    with pytest.raises(ValueError, match="需先导入遏制数据"):
        await advance_capa(db, capa, user.user_id, AdvanceRequest())


async def test_gate_rejects_missing_one_type(db, capa_d3_3types):
    capa, user = capa_d3_3types
    with pytest.raises(ValueError, match="4 类数据齐全"):
        await advance_capa(db, capa, user.user_id, AdvanceRequest())


async def test_gate_rejects_no_report_done(db, capa_d3_imported_no_done_report):
    capa, user = capa_d3_imported_no_done_report
    with pytest.raises(ValueError, match="报告已生成"):
        await advance_capa(db, capa, user.user_id, AdvanceRequest())


async def test_gate_rejects_no_execution(db, capa_d3_imported_4types_done_report):
    capa, user = capa_d3_imported_4types_done_report
    with pytest.raises(ValueError, match="记录遏制执行结果"):
        await advance_capa(db, capa, user.user_id, AdvanceRequest())


async def test_gate_passes_manual_execution_with_done_report(db, capa_d3_with_manual_execution):
    capa, user = capa_d3_with_manual_execution
    capa = await advance_capa(db, capa, user.user_id, AdvanceRequest())
    assert capa.status == "D4_ROOT_CAUSE"


async def test_gate_passes_never_generated_advice_pure_manual(db, capa_d3_pure_manual_no_advice):
    capa, user = capa_d3_pure_manual_no_advice
    capa = await advance_capa(db, capa, user.user_id, AdvanceRequest())
    assert capa.status == "D4_ROOT_CAUSE"


async def test_gate_rejects_old_generation_adopted_execution(db, capa_d3_regenerated_advice):
    capa, user = capa_d3_regenerated_advice
    with pytest.raises(ValueError, match="记录遏制执行结果"):
        await advance_capa(db, capa, user.user_id, AdvanceRequest())


async def test_gate_manual_unaffected_by_advice_regenerate(db, capa_d3_manual_after_advice_regenerate):
    capa, user = capa_d3_manual_after_advice_regenerate
    capa = await advance_capa(db, capa, user.user_id, AdvanceRequest())
    assert capa.status == "D4_ROOT_CAUSE"


async def test_gate_fails_after_execution_demote_to_failed(db, capa_d3_execution_demoted):
    capa, user = capa_d3_execution_demoted
    with pytest.raises(ValueError, match="记录遏制执行结果"):
        await advance_capa(db, capa, user.user_id, AdvanceRequest())


async def test_gate_rejects_failed_report(db, capa_d3_failed_report):
    capa, user = capa_d3_failed_report
    with pytest.raises(ValueError, match="报告已生成"):
        await advance_capa(db, capa, user.user_id, AdvanceRequest())


async def test_gate_rejects_superseded_report(db, capa_d3_superseded_report):
    capa, user = capa_d3_superseded_report
    with pytest.raises(ValueError, match="报告已生成"):
        await advance_capa(db, capa, user.user_id, AdvanceRequest())


async def test_gate_factory_mismatch_rejected(db, capa_d3_cross_factory_run):
    capa, user = capa_d3_cross_factory_run
    with pytest.raises(ValueError, match="工厂"):
        await advance_capa(db, capa, user.user_id, AdvanceRequest())
