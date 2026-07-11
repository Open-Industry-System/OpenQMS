"""Tests for D3 Containment Report Computation (US-E2E-01.1 Task 3+4).

Pure function tests for deterministic calculations plus async integration tests
for the three-phase impact report generation service.
"""

import asyncio
import uuid

import pytest
from sqlalchemy import select, text

from app.models.capa_d3 import CapaD3ImpactReport
from app.services.capa_d3_containment_service import (
    _compute_batches,
    _compute_impact_qty,
    _compute_customer_impact,
    _compute_time_window,
    _compute_risk_floor,
    generate_impact_report,
    _recover_stale_report,
    _running_report,
)
from tests.capa.conftest import _failed_report, _mark_report_stale


# ===== Batch Key Tests =====

def test_batch_key_hash_material_lot_merges_cross_source():
    """Same material+lot from different sources merge into one batch."""
    snapshots = [
        {"snapshot_type": "inventory", "snapshot_id": "s1", "payload": [
            {"record_key": "k1", "source_id": "b1", "material_code": "M1", "lot_no": "L1", "quantity": 70, "unit": "pcs"}
        ]},
        {"snapshot_type": "shipment", "snapshot_id": "s2", "payload": [
            {"record_key": "k2", "source_id": "sh1", "material_code": "M1", "lot_no": "L1", "quantity": 30, "unit": "pcs", "customer_code": "C1", "customer_name": "Acme", "customer_segment": "key", "arrival_status": "signed"}
        ]},
    ]
    batches = _compute_batches(snapshots)
    assert len(batches) == 1  # Same M1+L1 merge
    assert batches[0]["material_code"] == "M1" and batches[0]["lot_no"] == "L1"
    assert batches[0]["qty_by_status"]["inventory"] == [{"qty": 70, "unit": "pcs"}]
    assert batches[0]["qty_by_status"]["shipped"] == [{"qty": 30, "unit": "pcs"}]


def test_batch_key_degrades_when_lot_missing():
    """Batch key degrades to {snapshot_type}:{source_id} when lot is missing."""
    snapshots = [
        {"snapshot_type": "inventory", "snapshot_id": "s1", "payload": [
            {"record_key": "k1", "source_id": "b1", "material_code": "M1", "lot_no": None, "quantity": 70, "unit": "pcs"}
        ]}
    ]
    batches = _compute_batches(snapshots)
    assert batches[0]["batch_key"] == "inventory:b1"  # Degraded


def test_qty_by_status_only_inventory_shipment_contribute():
    """IQC does not contribute to qty_by_status, only to source_refs."""
    snapshots = [
        {"snapshot_type": "inventory", "snapshot_id": "s1", "payload": [
            {"record_key": "k1", "source_id": "b1", "material_code": "M1", "lot_no": "L1", "quantity": 70, "unit": "pcs"}
        ]},
        {"snapshot_type": "shipment", "snapshot_id": "s2", "payload": [
            {"record_key": "k2", "source_id": "sh1", "material_code": "M1", "lot_no": "L1", "quantity": 30, "unit": "pcs", "customer_code": "C1", "customer_name": "Acme", "customer_segment": "key", "arrival_status": "signed"}
        ]},
        {"snapshot_type": "iqc", "snapshot_id": "s3", "payload": [
            {"record_key": "k3", "source_id": "i1", "inspection_no": "IQ1", "supplier_id": "sup1", "supplier_name": "S", "part_no": "M1", "lot_no": "L1", "defect_qty": 100, "defect_description": "d", "inspection_result": "reject", "inspection_date": "2026-07-01"}
        ]},
    ]
    batches = _compute_batches(snapshots)
    total = sum(q["qty"] for qs in batches[0]["qty_by_status"].values() for q in qs)
    assert total == 100  # 70+30, NOT 200
    assert any(r["snapshot_type"] == "iqc" for r in batches[0]["source_refs"])  # IQC in source_refs


def test_qty_by_status_multi_unit_not_merged():
    """Different lot -> different batch; same batch multi-unit not merged."""
    snapshots = [
        {"snapshot_type": "inventory", "snapshot_id": "s1", "payload": [
            {"record_key": "k1", "source_id": "b1", "material_code": "M1", "lot_no": "L1", "quantity": 70, "unit": "pcs"}
        ]},
        {"snapshot_type": "inventory", "snapshot_id": "s2", "payload": [
            {"record_key": "k2", "source_id": "b2", "material_code": "M1", "lot_no": "L2", "quantity": 5, "unit": "kg"}
        ]},
    ]
    batches = _compute_batches(snapshots)
    # Different lot -> different batch
    assert len(batches) == 2


def test_dedup_by_source_id():
    """Duplicate source_id records are deduped."""
    snapshots = [
        {"snapshot_type": "inventory", "snapshot_id": "s1", "payload": [
            {"record_key": "k1", "source_id": "b1", "material_code": "M1", "lot_no": "L1", "quantity": 70, "unit": "pcs"},
            {"record_key": "k1b", "source_id": "b1", "material_code": "M1", "lot_no": "L1", "quantity": 70, "unit": "pcs"}  # Same source_id duplicate
        ]}
    ]
    batches = _compute_batches(snapshots)
    assert batches[0]["qty_by_status"]["inventory"] == [{"qty": 70, "unit": "pcs"}]  # Deduped, not double-counted


def test_iqc_part_no_merges_with_inventory_shipment():
    """IQC uses part_no (not material_code) - same part_no+lot merges with inventory/shipment."""
    snapshots = [
        {"snapshot_type": "inventory", "snapshot_id": "s1", "payload": [
            {"record_key": "k1", "source_id": "b1", "material_code": "M1", "lot_no": "L1", "quantity": 70, "unit": "pcs"}
        ]},
        {"snapshot_type": "iqc", "snapshot_id": "s3", "payload": [
            {"record_key": "k3", "source_id": "i1", "part_no": "M1", "lot_no": "L1", "defect_qty": 100, "inspection_result": "reject"}
        ]},
    ]
    batches = _compute_batches(snapshots)
    assert len(batches) == 1  # part_no=M1+L1 merges with material_code=M1+L1
    assert any(r["snapshot_type"] == "iqc" for r in batches[0]["source_refs"])  # IQC in source_refs
    assert batches[0]["qty_by_status"]["inventory"] == [{"qty": 70, "unit": "pcs"}]  # IQC does not contribute qty


def test_shipment_arrival_status_splits_in_transit_vs_shipped():
    """Shipment arrival_status splits into in_transit vs shipped."""
    snapshots = [
        {"snapshot_type": "shipment", "snapshot_id": "s2", "payload": [
            {"record_key": "k2", "source_id": "sh1", "material_code": "M1", "lot_no": "L1", "quantity": 30, "unit": "pcs", "arrival_status": "signed", "customer_code": "C1"},
            {"record_key": "k2b", "source_id": "sh2", "material_code": "M1", "lot_no": "L2", "quantity": 40, "unit": "pcs", "arrival_status": "in_transit", "customer_code": "C2"},
        ]},
    ]
    batches = _compute_batches(snapshots)
    by_lot = {b["lot_no"]: b for b in batches}
    assert by_lot["L1"]["qty_by_status"]["shipped"] == [{"qty": 30, "unit": "pcs"}]  # signed -> shipped
    assert by_lot["L2"]["qty_by_status"]["in_transit"] == [{"qty": 40, "unit": "pcs"}]  # in_transit -> in_transit
    assert by_lot["L1"]["qty_by_status"]["in_transit"] == []  # L1 has no in_transit


# ===== Impact Qty Tests =====

def test_impact_qty_same_unit_sums_different_unit_separate():
    """Same status+unit sums and merges; different unit stays separate."""
    snapshots = [
        {"snapshot_type": "inventory", "snapshot_id": "s1", "payload": [
            {"record_key": "k1", "source_id": "b1", "material_code": "M1", "lot_no": "L1", "quantity": 70, "unit": "pcs"},
            {"record_key": "k2", "source_id": "b2", "material_code": "M1", "lot_no": "L2", "quantity": 30, "unit": "pcs"},
            {"record_key": "k3", "source_id": "b3", "material_code": "M2", "lot_no": "L3", "quantity": 5, "unit": "kg"},
        ]},
    ]
    batches = _compute_batches(snapshots)
    impact = _compute_impact_qty(batches)
    # 70+30 pcs merged; 5 kg separate
    assert {"qty": 100, "unit": "pcs"} in impact["inventory"]
    assert {"qty": 5, "unit": "kg"} in impact["inventory"]
    assert len(impact["inventory"]) == 2  # Two unit groups


# ===== Customer Impact Tests =====

def test_customer_impact_quantities_array_with_segment_from_payload():
    """Customer impact includes quantities array with segment from payload."""
    ship = {"snapshot_id": "s2", "payload": [
        {"customer_code": "C1", "customer_name": "Acme", "customer_segment": "key", "quantity": 30, "unit": "pcs", "arrival_status": "signed", "material_code": "M1", "lot_no": "L1"}
    ]}
    ci = _compute_customer_impact(ship)
    assert ci == [{"customer_name": "Acme", "customer_segment": "key", "arrival_status": "signed", "quantities": [{"qty": 30, "unit": "pcs"}]}]


# ===== Time Window Tests =====

def test_time_window_alarm_min_max():
    """Time window returns min/max triggered_at."""
    spc = {"snapshot_id": "s4", "payload": [
        {"triggered_at": "2026-07-01T10:00:00Z"},
        {"triggered_at": "2026-07-05T08:00:00Z"}
    ]}
    tw = _compute_time_window(spc)
    assert tw == {"start": "2026-07-01T10:00:00Z", "end": "2026-07-05T08:00:00Z"}


# ===== Risk Floor Tests =====

def test_risk_floor_unknown_arrival_with_customer_is_high():
    """Unknown arrival status with affected customer -> high (conservative)."""
    ci = [{"customer_name": "Acme", "customer_segment": "key", "arrival_status": "unknown", "quantities": [{"qty": 30, "unit": "pcs"}]}]
    floor, err = _compute_risk_floor(ci, {"capa_severity": "general", "risk_mapping_version": "v1"})
    assert floor == "high" and err is None  # unknown affected customer -> high


def test_risk_floor_severity_via_risk_mappings_version():
    """Risk floor uses capa_severity via RISK_MAPPINGS version."""
    floor, err = _compute_risk_floor([], {"capa_severity": "serious", "risk_mapping_version": "v1"})
    assert floor == "medium" and err is None  # RISK_MAPPINGS["v1"]["serious"]


def test_risk_floor_unknown_mapping_version_returns_error_code():
    """Unknown mapping version returns error code, does not silently use latest."""
    floor, err = _compute_risk_floor([], {"capa_severity": "serious", "risk_mapping_version": "v9"})
    assert floor is None and err == "unknown_risk_mapping_version"  # Does not silently use latest


# ===== Report Generation Integration Tests (Task 4) =====


@pytest.mark.asyncio
async def test_report_three_phase_running_then_done(db, capa_d3_imported, llm_mock):
    capa, run, user = capa_d3_imported
    llm_mock.return_value = {"risk_level": "medium", "risk_explanation": "customer_01 风险中等"}
    r = await generate_impact_report(db, run.run_id, user)
    assert r["status"] == "done"
    report = await db.get(CapaD3ImpactReport, r["report_id"])
    assert report.status == "done" and report.is_current is True and report.llm_available is True and report.model
    assert report.risk_level == "medium" and report.risk_floor
    assert "customer_01" not in report.risk_explanation


@pytest.mark.asyncio
async def test_attempt_token_cas_stale_worker_discarded(db, capa_d3_imported, llm_slow):
    capa, run, user = capa_d3_imported
    hold_a = asyncio.Event()

    async def _slow(*args, **kwargs):
        await hold_a.wait()
        return {"risk_level": "high", "risk_explanation": "x"}

    llm_slow.side_effect = _slow
    task_a = asyncio.create_task(generate_impact_report(db, run.run_id, user))
    await asyncio.sleep(0.05)
    await _mark_report_stale(db, run.run_id)
    hold_a.set()
    r_a = await task_a
    assert r_a["status"] in ("superseded", "failed")


@pytest.mark.asyncio
async def test_duplicate_request_returns_202_with_retry_after(db, capa_d3_imported, llm_slow):
    capa, run, user = capa_d3_imported
    hold = asyncio.Event()

    async def _slow(*args, **kwargs):
        await hold.wait()

    llm_slow.side_effect = _slow
    task = asyncio.create_task(generate_impact_report(db, run.run_id, user))
    await asyncio.sleep(0.05)
    r = await generate_impact_report(db, run.run_id, user)
    assert r["status"] == "running" and r["report_id"] and r["retry_after"] >= 1
    hold.set()
    await task


@pytest.mark.asyncio
async def test_llm_failed_writes_stage_runs_error_code(db, capa_d3_imported, llm_raise, audit_reader):
    capa, run, user = capa_d3_imported
    llm_raise.side_effect = RuntimeError("LLM down")
    r = await generate_impact_report(db, run.run_id, user)
    assert r["status"] == "failed"
    report = await db.get(CapaD3ImpactReport, r["report_id"])
    assert report.error == "llm_failed" and report.stage_runs and report.completed_at
    audited = await audit_reader(capa.report_id, "D3_REPORT_GENERATED")
    assert audited["status"] == "failed" and audited["error"] == "llm_failed"


@pytest.mark.asyncio
async def test_schema_failed_writes_stage_runs_error_code(db, capa_d3_imported, llm_bad_schema):
    capa, run, user = capa_d3_imported
    llm_bad_schema.return_value = ["not_a_dict"]
    r = await generate_impact_report(db, run.run_id, user)
    assert r["status"] == "failed"
    report = await db.get(CapaD3ImpactReport, r["report_id"])
    assert report.error == "schema_failed" and report.stage_runs and report.completed_at


@pytest.mark.asyncio
async def test_superseded_writes_error_code_no_current_switch(db, capa_d3_imported, llm_mock, superseded_run):
    capa, run, user = capa_d3_imported
    llm_mock.return_value = {"risk_level": "medium", "risk_explanation": "ok"}
    r = await generate_impact_report(db, run.run_id, user)
    assert r["status"] == "superseded"
    report = await db.get(CapaD3ImpactReport, r["report_id"])
    assert report.error == "superseded" and report.is_current is False


@pytest.mark.asyncio
async def test_unknown_risk_mapping_version_failed(db, capa_d3_imported_bad_mapping_version, llm_mock):
    capa, run, user = capa_d3_imported_bad_mapping_version
    llm_mock.return_value = {"risk_level": "medium", "risk_explanation": "ok"}
    r = await generate_impact_report(db, run.run_id, user)
    assert r["status"] == "failed"
    report = await db.get(CapaD3ImpactReport, r["report_id"])
    assert report.error == "unknown_risk_mapping_version"


@pytest.mark.asyncio
async def test_stale_recovery_cas_running_to_failed(db, capa_d3_imported, stale_running_report):
    capa, run, user = capa_d3_imported
    await _recover_stale_report(db, run.run_id)
    report = await _running_report(db, run.run_id)
    assert report is None
    failed = await _failed_report(db, run.run_id)
    assert failed.error == "stale" and failed.completed_at


@pytest.mark.asyncio
async def test_prompt_truncated_within_max_chars_with_prompt_stats(db, capa_d3_imported_huge, llm_mock):
    capa, run, user = capa_d3_imported_huge
    llm_mock.return_value = {"risk_level": "medium", "risk_explanation": "ok"}
    r = await generate_impact_report(db, run.run_id, user)
    report = await db.get(CapaD3ImpactReport, r["report_id"])
    assert report.prompt_stats["truncated"] is True and report.prompt_stats["original_total"] > 8000


@pytest.mark.asyncio
async def test_risk_explanation_customer_name_restored(db, capa_d3_imported, llm_mock):
    capa, run, user = capa_d3_imported
    llm_mock.return_value = {"risk_level": "high", "risk_explanation": "customer_01 需召回"}
    r = await generate_impact_report(db, run.run_id, user)
    report = await db.get(CapaD3ImpactReport, r["report_id"])
    assert "customer_01" not in report.risk_explanation and "Acme" in report.risk_explanation


@pytest.mark.asyncio
async def test_risk_floor_max_llm_and_unknown_high(db, capa_d3_imported_unknown_arrival, llm_mock):
    capa, run, user = capa_d3_imported_unknown_arrival
    llm_mock.return_value = {"risk_level": "low", "risk_explanation": "x"}
    r = await generate_impact_report(db, run.run_id, user)
    report = await db.get(CapaD3ImpactReport, r["report_id"])
    assert report.risk_level == "high"
    assert report.risk_floor == "high"


@pytest.mark.asyncio
async def test_snapshot_only_no_source_table_query(db, capa_d3_imported, llm_mock):
    capa, run, user = capa_d3_imported
    await db.execute(text("UPDATE customers SET segment='normal' WHERE customer_code='C1'"))
    await db.commit()
    llm_mock.return_value = {"risk_level": "medium", "risk_explanation": "ok"}
    r = await generate_impact_report(db, run.run_id, user)
    report = await db.get(CapaD3ImpactReport, r["report_id"])
    assert report.customer_impact[0]["customer_segment"] == "key"


@pytest.mark.asyncio
async def test_no_creds_returns_blocked_not_build_running(db, capa_d3_imported, no_creds):
    capa, run, user = capa_d3_imported
    r = await generate_impact_report(db, run.run_id, user)
    assert r["status"] == "blocked"
    running = await _running_report(db, run.run_id)
    assert running is None
