"""Regression coverage for deleting dynamic CAPA D3 containment chains."""
import pytest
from sqlalchemy import select

from app.api.e2e import cleanup_test_data
from app.models.capa import CAPAEightD
from app.models.capa_d3 import (
    CapaD3AdviceAdoption,
    CapaD3AdviceGeneration,
    CapaD3AiAdvice,
    CapaD3ContainmentSnapshot,
    CapaD3Execution,
    CapaD3ImpactReport,
    CapaD3ImportRun,
)


@pytest.mark.requires_db
async def test_cleanup_deletes_prefixed_capa_d3_chain(db, default_factory, admin_user):
    """CAPA cleanup removes every RESTRICT-linked D3 descendant before its CAPA."""
    prefix = "E2E-CLEAN-D3-"
    capa = CAPAEightD(
        document_no=f"{prefix}CAPA",
        title="D3 cleanup regression",
        factory_id=default_factory.id,
        created_by=admin_user.user_id,
    )
    db.add(capa)
    await db.flush()

    run = CapaD3ImportRun(
        capa_id=capa.report_id,
        factory_id=default_factory.id,
        analysis_context={},
        imported_by=admin_user.user_id,
    )
    db.add(run)
    await db.flush()

    snapshot = CapaD3ContainmentSnapshot(
        run_id=run.run_id,
        factory_id=default_factory.id,
        snapshot_type="inventory",
        payload=[],
        imported_by=admin_user.user_id,
    )
    db.add(snapshot)

    report = CapaD3ImpactReport(
        run_id=run.run_id,
        factory_id=default_factory.id,
        generated_by=admin_user.user_id,
    )
    db.add(report)
    await db.flush()

    generation = CapaD3AdviceGeneration(
        report_id=report.report_id,
        factory_id=default_factory.id,
        generated_by=admin_user.user_id,
    )
    db.add(generation)
    await db.flush()

    advice = CapaD3AiAdvice(
        generation_id=generation.generation_id,
        factory_id=default_factory.id,
        advice_type="isolate",
        advice_text="Contain the affected material",
        source_provenance=[],
        generated_by=admin_user.user_id,
    )
    db.add(advice)
    await db.flush()

    adoption = CapaD3AdviceAdoption(
        advice_id=advice.advice_id,
        factory_id=default_factory.id,
        decision="adopted",
        adopted_text="Contain the affected material",
        advice_type="isolate",
        source_provenance=[],
        decided_by=admin_user.user_id,
    )
    execution = CapaD3Execution(
        report_id=report.report_id,
        generation_id=generation.generation_id,
        advice_id=advice.advice_id,
        factory_id=default_factory.id,
        source="adopted",
        measure_text="Contain the affected material",
        result_status="pending",
        evidence_refs=[],
        executed_by=admin_user.user_id,
    )
    db.add_all([adoption, execution])
    await db.flush()

    response = await cleanup_test_data(prefix, db)

    assert response["deleted"]["CAPAEightD"] == 1
    for model_name in [
        "CapaD3AdviceAdoption",
        "CapaD3Execution",
        "CapaD3AiAdvice",
        "CapaD3AdviceGeneration",
        "CapaD3ImpactReport",
        "CapaD3ContainmentSnapshot",
        "CapaD3ImportRun",
    ]:
        assert response["deleted"][model_name] == 1
    for model, pk_col, row_id in [
        (CAPAEightD, CAPAEightD.report_id, capa.report_id),
        (CapaD3ImportRun, CapaD3ImportRun.run_id, run.run_id),
        (CapaD3ContainmentSnapshot, CapaD3ContainmentSnapshot.snapshot_id, snapshot.snapshot_id),
        (CapaD3ImpactReport, CapaD3ImpactReport.report_id, report.report_id),
        (CapaD3AdviceGeneration, CapaD3AdviceGeneration.generation_id, generation.generation_id),
        (CapaD3AiAdvice, CapaD3AiAdvice.advice_id, advice.advice_id),
        (CapaD3AdviceAdoption, CapaD3AdviceAdoption.adoption_id, adoption.adoption_id),
        (CapaD3Execution, CapaD3Execution.execution_id, execution.execution_id),
    ]:
        assert await db.scalar(select(model).where(pk_col == row_id)) is None
