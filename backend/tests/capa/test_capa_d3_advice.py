"""Tests for D3 Containment Advice Generation (US-E2E-01.1 Task 7).

Three-phase advice generation service tests:
- Phase 1: credential check, CAPA lock, running generation creation
- Phase 2: LLM call with schema validation and provenance mapping
- Phase 3: CAS promotion with attempt_token, advice row insertion, audit

Key invariants:
- Accepted advice is filtered by batch_key existence in report.batches
- Provenance mapping is advice_type-specific (recall->shipment, etc.)
- record_key is never null (only snapshot_id may be null for report-level)
- Empty accepted_advice -> failed (all_provenance_mapping_failed), no current switch
- Every terminal transition writes audit log
"""

import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.models.capa_d3 import CapaD3AdviceGeneration, CapaD3AiAdvice
from app.schemas.capa_d3 import D3AdviceRequest
from app.services.capa_d3_containment_service import (
    generate_advice,
    _recover_stale_advice_generation,
    _running_advice_generation,
    _map_provenance,
    _build_advice_prompt,
    _restore_customer_names,
)
from tests.capa.conftest import _mark_advice_generation_stale


async def _failed_advice_generation(db, report_id):
    """Return the latest failed advice generation for a report."""
    from sqlalchemy import desc
    return await db.scalar(
        select(CapaD3AdviceGeneration)
        .where(
            CapaD3AdviceGeneration.report_id == report_id,
            CapaD3AdviceGeneration.status == "failed",
        )
        .order_by(desc(CapaD3AdviceGeneration.completed_at))
    )


# ===== Basic flow tests =====


@pytest.mark.asyncio
async def test_advice_three_phase_running_then_done(db, capa_d3_done_report, llm_mock):
    capa, report, run, user = capa_d3_done_report
    batch_key = report.batches[0]["batch_key"] if report.batches else None
    llm_mock.return_value = {
        "advice": [{
            "advice_type": "recall",
            "advice_text": "建议召回批次 customer_01",
            "target_batch_refs": [batch_key] if batch_key else None,
            "provenance_sources_hint": ["shipment"],
        }]
    }
    r = await generate_advice(db, capa.report_id, report.report_id, user, D3AdviceRequest())
    assert r["status"] == "done" and r["advice_count"] >= 1, f"Got {r}"
    gen = await db.get(CapaD3AdviceGeneration, r["generation_id"])
    assert gen.status == "done" and gen.is_current is True and gen.llm_available is True and gen.model
    assert gen.advice_count >= 1
    assert gen.rejected_advice_count == 0


@pytest.mark.asyncio
async def test_advice_done_check_requires_advice_count_and_llm(db, capa_d3_done_report, llm_mock):
    capa, report, run, user = capa_d3_done_report
    batch_key = report.batches[0]["batch_key"] if report.batches else None
    llm_mock.return_value = {
        "advice": [{
            "advice_type": "recall",
            "advice_text": "t",
            "target_batch_refs": [batch_key] if batch_key else None,
            "provenance_sources_hint": ["shipment"],
        }]
    }
    r = await generate_advice(db, capa.report_id, report.report_id, user, D3AdviceRequest())
    gen = await db.get(CapaD3AdviceGeneration, r["generation_id"])
    assert gen.advice_count > 0 and gen.llm_available is True


# ===== Concurrency tests =====


@pytest.mark.asyncio
async def test_attempt_token_cas_stale_worker_discarded(db, capa_d3_done_report, llm_slow):
    capa, report, run, user = capa_d3_done_report
    batch_key = report.batches[0]["batch_key"] if report.batches else None
    hold = asyncio.Event()

    async def _slow(*a, **k):
        await hold.wait()
        return {
            "advice": [{
                "advice_type": "recall",
                "advice_text": "t",
                "target_batch_refs": [batch_key] if batch_key else None,
                "provenance_sources_hint": ["shipment"],
            }]
        }

    llm_slow.side_effect = _slow
    task_a = asyncio.create_task(generate_advice(db, capa.report_id, report.report_id, user, D3AdviceRequest()))
    await asyncio.sleep(0.05)
    await _mark_advice_generation_stale(db, report.report_id)
    hold.set()
    r_a = await task_a  # Ensure task completes
    assert r_a["status"] in ("superseded", "failed")


@pytest.mark.asyncio
async def test_duplicate_request_202_with_retry_after(db, capa_d3_done_report, llm_slow):
    capa, report, run, user = capa_d3_done_report
    batch_key = report.batches[0]["batch_key"] if report.batches else None
    hold = asyncio.Event()

    async def _slow(*a, **k):
        await hold.wait()
        return {
            "advice": [{
                "advice_type": "recall",
                "advice_text": "t",
                "target_batch_refs": [batch_key] if batch_key else None,
                "provenance_sources_hint": ["shipment"],
            }]
        }

    llm_slow.side_effect = _slow
    task = asyncio.create_task(generate_advice(db, capa.report_id, report.report_id, user, D3AdviceRequest()))
    await asyncio.sleep(0.05)
    r = await generate_advice(db, capa.report_id, report.report_id, user, D3AdviceRequest())
    assert r["status"] == "running" and r["generation_id"] and r["retry_after"] >= 1, f"Got {r}"
    hold.set()
    await task  # Ensure task completes before teardown


# ===== Credential guard =====


@pytest.mark.asyncio
async def test_no_creds_422_no_generation_built(db, capa_d3_done_report, no_creds):
    capa, report, run, user = capa_d3_done_report
    r = await generate_advice(db, capa.report_id, report.report_id, user, D3AdviceRequest())
    assert r["status"] == "blocked"
    gens = (await db.execute(select(CapaD3AdviceGeneration).where(CapaD3AdviceGeneration.report_id == report.report_id))).scalars().all()
    assert len(gens) == 0


# ===== Provenance mapping tests =====


@pytest.mark.asyncio
async def test_provenance_recall_maps_shipment_snapshot(db, capa_d3_done_report, llm_mock):
    capa, report, run, user = capa_d3_done_report
    batch_key = report.batches[0]["batch_key"]
    llm_mock.return_value = {
        "advice": [{"advice_type": "recall", "advice_text": "t", "target_batch_refs": [batch_key], "provenance_sources_hint": ["shipment"]}]
    }
    r = await generate_advice(db, capa.report_id, report.report_id, user, D3AdviceRequest())
    advice = (await db.execute(select(CapaD3AiAdvice).where(CapaD3AiAdvice.generation_id == r["generation_id"]))).scalars().first()
    assert advice.source_provenance[0]["source_type"] == "shipment"
    assert advice.source_provenance[0]["snapshot_id"]
    assert advice.source_provenance[0]["record_key"]


@pytest.mark.asyncio
async def test_provenance_recall_batch_level_trace_targets_hit_record(db, capa_d3_two_shipment_batches_report, llm_mock):
    capa, report, run, user = capa_d3_two_shipment_batches_report
    batch_b = next(b for b in report.batches if any(r["snapshot_type"] == "shipment" for r in b["source_refs"]))
    expected_rk = next(r["record_key"] for r in batch_b["source_refs"] if r["snapshot_type"] == "shipment")
    llm_mock.return_value = {
        "advice": [{"advice_type": "recall", "advice_text": "t", "target_batch_refs": [batch_b["batch_key"]], "provenance_sources_hint": ["shipment"]}]
    }
    r = await generate_advice(db, capa.report_id, report.report_id, user, D3AdviceRequest())
    advice = (await db.execute(select(CapaD3AiAdvice).where(CapaD3AiAdvice.generation_id == r["generation_id"]))).scalars().first()
    hit_keys = {p["record_key"] for p in advice.source_provenance}
    assert expected_rk in hit_keys
    batch_a_rk = next(
        (r["record_key"] for b in report.batches if b["batch_key"] != batch_b["batch_key"]
         for r in b["source_refs"] if r["snapshot_type"] == "shipment"), None
    )
    if batch_a_rk:
        assert batch_a_rk not in hit_keys


@pytest.mark.asyncio
async def test_provenance_isolate_maps_inventory(db, capa_d3_done_report, llm_mock):
    capa, report, run, user = capa_d3_done_report
    batch_key = report.batches[0]["batch_key"]
    llm_mock.return_value = {
        "advice": [{"advice_type": "isolate", "advice_text": "t", "target_batch_refs": [batch_key], "provenance_sources_hint": ["inventory"]}]
    }
    r = await generate_advice(db, capa.report_id, report.report_id, user, D3AdviceRequest())
    advice = (await db.execute(select(CapaD3AiAdvice).where(CapaD3AiAdvice.generation_id == r["generation_id"]))).scalars().first()
    assert advice.source_provenance[0]["source_type"] == "inventory"
    assert advice.source_provenance[0]["record_key"]


@pytest.mark.asyncio
async def test_provenance_strict_inspection_maps_iqc(db, capa_d3_done_report, llm_mock):
    capa, report, run, user = capa_d3_done_report
    llm_mock.return_value = {
        "advice": [{"advice_type": "strict_inspection", "advice_text": "t", "target_batch_refs": None, "provenance_sources_hint": ["iqc"]}]
    }
    r = await generate_advice(db, capa.report_id, report.report_id, user, D3AdviceRequest())
    advice = (await db.execute(select(CapaD3AiAdvice).where(CapaD3AiAdvice.generation_id == r["generation_id"]))).scalars().first()
    assert advice.source_provenance[0]["source_type"] == "iqc"
    assert advice.source_provenance[0]["record_key"]


@pytest.mark.asyncio
async def test_provenance_alternative_report_level_record_key_nonempty(db, capa_d3_done_report, llm_mock):
    capa, report, run, user = capa_d3_done_report
    llm_mock.return_value = {
        "advice": [{"advice_type": "alternative", "advice_text": "t", "target_batch_refs": None, "provenance_sources_hint": []}]
    }
    r = await generate_advice(db, capa.report_id, report.report_id, user, D3AdviceRequest())
    advice = (await db.execute(select(CapaD3AiAdvice).where(CapaD3AiAdvice.generation_id == r["generation_id"]))).scalars().first()
    assert advice.source_provenance[0]["source_type"] == "report"
    assert advice.source_provenance[0]["snapshot_id"] is None
    assert advice.source_provenance[0]["record_key"] == f"report:{report.report_id}:summary"


@pytest.mark.asyncio
async def test_record_key_never_null_only_snapshot_id_nullable(db, capa_d3_done_report, llm_mock):
    capa, report, run, user = capa_d3_done_report
    llm_mock.return_value = {
        "advice": [{"advice_type": "alternative", "advice_text": "t", "target_batch_refs": None, "provenance_sources_hint": []}]
    }
    r = await generate_advice(db, capa.report_id, report.report_id, user, D3AdviceRequest())
    advice = (await db.execute(select(CapaD3AiAdvice).where(CapaD3AiAdvice.generation_id == r["generation_id"]))).scalars().all()
    for a in advice:
        for p in a.source_provenance:
            assert p["record_key"]


# ===== Filtering / rejection tests =====


@pytest.mark.asyncio
async def test_target_batch_refs_must_exist_in_batches(db, capa_d3_done_report, llm_mock):
    capa, report, run, user = capa_d3_done_report
    # Use a batch_key that definitely exists
    valid_batch_key = report.batches[0]["batch_key"] if report.batches else "dummy"
    # Return advice with an invalid target_batch_ref
    llm_mock.return_value = {
        "advice": [{
            "advice_type": "recall",
            "advice_text": "t",
            "target_batch_refs": ["nonexistent_key"],
            "provenance_sources_hint": ["shipment"],
        }]
    }
    r = await generate_advice(db, capa.report_id, report.report_id, user, D3AdviceRequest())
    # Should fail with all_provenance_mapping_failed since batch_key doesn't exist
    assert r["status"] == "failed" and r.get("rejected_advice_count", 0) >= 1, f"Got {r}"


@pytest.mark.asyncio
async def test_advice_text_customer_name_restored(db, capa_d3_done_report, llm_mock):
    capa, report, run, user = capa_d3_done_report
    batch_key = report.batches[0]["batch_key"]
    llm_mock.return_value = {
        "advice": [{"advice_type": "recall", "advice_text": "召回 customer_01 批次", "target_batch_refs": [batch_key], "provenance_sources_hint": ["shipment"]}]
    }
    r = await generate_advice(db, capa.report_id, report.report_id, user, D3AdviceRequest())
    advice = (await db.execute(select(CapaD3AiAdvice).where(CapaD3AiAdvice.generation_id == r["generation_id"]))).scalars().first()
    assert "customer_01" not in advice.advice_text
    assert "Acme" in advice.advice_text


@pytest.mark.asyncio
async def test_all_provenance_failed_returns_200_failed_no_current_switch(db, capa_d3_done_report, llm_mock):
    capa, report, run, user = capa_d3_done_report
    llm_mock.return_value = {
        "advice": [{"advice_type": "recall", "advice_text": "t", "target_batch_refs": ["nonexistent"], "provenance_sources_hint": ["shipment"]}]
    }
    r = await generate_advice(db, capa.report_id, report.report_id, user, D3AdviceRequest())
    assert r["status"] == "failed"
    gen = await db.get(CapaD3AdviceGeneration, r["generation_id"])
    assert gen.is_current is False
    assert gen.error == "all_provenance_mapping_failed"


@pytest.mark.asyncio
async def test_partial_filtered_accepted_nonempty_advances(db, capa_d3_done_report, llm_mock):
    capa, report, run, user = capa_d3_done_report
    batch_key = report.batches[0]["batch_key"]
    llm_mock.return_value = {
        "advice": [
            {"advice_type": "recall", "advice_text": "t", "target_batch_refs": [batch_key], "provenance_sources_hint": ["shipment"]},
            {"advice_type": "recall", "advice_text": "t", "target_batch_refs": ["nonexistent"], "provenance_sources_hint": ["shipment"]},
        ]
    }
    r = await generate_advice(db, capa.report_id, report.report_id, user, D3AdviceRequest())
    assert r["status"] == "done" and r["advice_count"] == 1 and r["rejected_advice_count"] == 1


@pytest.mark.asyncio
async def test_filtered_advice_stage_runs_persisted_db_readable(db, capa_d3_done_report, llm_mock):
    capa, report, run, user = capa_d3_done_report
    llm_mock.return_value = {
        "advice": [{"advice_type": "recall", "advice_text": "t", "target_batch_refs": ["nonexistent"], "provenance_sources_hint": ["shipment"]}]
    }
    r = await generate_advice(db, capa.report_id, report.report_id, user, D3AdviceRequest())
    gen = await db.get(CapaD3AdviceGeneration, r["generation_id"])
    assert gen.stage_runs and any(e.get("rejection_reason") for e in gen.stage_runs)
    assert gen.rejected_advice_count == 1


# ===== Error handling tests =====


@pytest.mark.asyncio
async def test_llm_failed_writes_stage_runs_error_code(db, capa_d3_done_report, llm_raise, audit_reader):
    capa, report, run, user = capa_d3_done_report
    llm_raise.side_effect = RuntimeError("down")
    r = await generate_advice(db, capa.report_id, report.report_id, user, D3AdviceRequest())
    gen = await db.get(CapaD3AdviceGeneration, r["generation_id"])
    assert gen.error == "llm_failed" and gen.stage_runs and gen.completed_at
    audited = await audit_reader(capa.report_id, "D3_AI_ADVICE_GENERATED")
    assert audited["status"] == "failed" and audited["error"] == "llm_failed"


@pytest.mark.asyncio
async def test_schema_failed_writes_stage_runs_error_code(db, capa_d3_done_report, llm_bad_schema):
    capa, report, run, user = capa_d3_done_report
    llm_bad_schema.return_value = {"not_an_array": True}
    r = await generate_advice(db, capa.report_id, report.report_id, user, D3AdviceRequest())
    gen = await db.get(CapaD3AdviceGeneration, r["generation_id"])
    assert gen.error == "schema_failed"


@pytest.mark.asyncio
async def test_superseded_writes_error_code_no_current_switch(db, capa_d3_done_report, llm_mock, superseded_report):
    capa, report, run, user = capa_d3_done_report
    r = await generate_advice(db, capa.report_id, report.report_id, user, D3AdviceRequest())
    assert r["status"] == "superseded"
    gen = await db.get(CapaD3AdviceGeneration, r["generation_id"])
    assert gen.error == "superseded" and gen.is_current is False


@pytest.mark.asyncio
async def test_stale_recovery_cas_running_to_failed(db, capa_d3_done_report, stale_running_generation):
    capa, report, run, user = capa_d3_done_report
    await _recover_stale_advice_generation(db, report.report_id)
    running = await _running_advice_generation(db, report.report_id)
    assert running is None
    failed = await _failed_advice_generation(db, report.report_id)
    assert failed.error == "stale" and failed.completed_at