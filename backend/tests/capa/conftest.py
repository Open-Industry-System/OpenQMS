"""Shared fixtures for D3 containment tests (US-E2E-01.1 Task 4)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import desc, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock

from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.capa_d3 import (
    CapaD3ImportRun,
    CapaD3ImpactReport,
    CapaD3ContainmentSnapshot,
    CapaD3AdviceGeneration,
)
from app.models.capa_doc_gate import CapaDocgAnalysis
from app.models.customer_quality import Customer
from app.models.erp import ERPConnection, ERPInventoryBalance, ERPShipment
from app.models.factory import Factory
from app.models.iqc_inspection import IqcInspection
from app.models.role import RoleDefinition
from app.models.spc import InspectionCharacteristic, SPCAlarm
from app.models.supplier import Supplier
from app.models.user import User
from app.services.agent import provider_adapter
from app.services.agent.provider_adapter import ProviderNotConfiguredError
from app.services.capa_d3_containment_service import (
    generate_impact_report,
    import_containment_data,
)


# ===== Test-only helpers =====


async def _failed_report(db: AsyncSession, run_id: uuid.UUID):
    """Return the latest failed report for a run."""
    return await db.scalar(
        select(CapaD3ImpactReport)
        .where(
            CapaD3ImpactReport.run_id == run_id,
            CapaD3ImpactReport.status == "failed",
        )
        .order_by(desc(CapaD3ImpactReport.completed_at))
    )


async def _mark_report_stale(db: AsyncSession, run_id: uuid.UUID):
    """CAS a running report to failed (simulate preemption)."""
    await db.execute(
        update(CapaD3ImpactReport)
        .where(
            CapaD3ImpactReport.run_id == run_id,
            CapaD3ImpactReport.status == "running",
        )
        .values(
            status="failed",
            error="stale",
            completed_at=datetime.now(timezone.utc),
            stage_runs=[{"stage": "stale_recovery", "error": "marked stale by test"}],
        )
    )
    await db.commit()


async def _mark_advice_generation_stale(db: AsyncSession, report_id: uuid.UUID):
    """CAS a running advice generation to failed (simulate preemption)."""
    await db.execute(
        update(CapaD3AdviceGeneration)
        .where(
            CapaD3AdviceGeneration.report_id == report_id,
            CapaD3AdviceGeneration.status == "running",
        )
        .values(
            status="failed",
            error="stale",
            completed_at=datetime.now(timezone.utc),
            stage_runs=[{"stage": "stale_recovery", "error": "marked stale by test"}],
        )
    )
    await db.commit()


# ===== Base fixtures =====


@pytest_asyncio.fixture
async def capa_d3_setup(db: AsyncSession):
    """Create a CAPA in D3_INTERIM status with factory + user."""
    factory = Factory(
        id=uuid.uuid4(),
        code="FAC-D3",
        name="D3 Test Factory",
        is_active=True,
    )
    db.add(factory)
    await db.flush()

    role = RoleDefinition(
        id=uuid.uuid4(),
        role_key="test_role_d3",
        name_zh="测试角色",
        name_en="Test Role D3",
        description="Test role for D3 tests",
        is_system=False,
        is_editable=True,
        is_active=True,
    )
    db.add(role)
    await db.flush()

    user = User(
        user_id=uuid.uuid4(),
        username="test_d3_user",
        display_name="Test D3 User",
        email="test@example.com",
        password_hash="test_hash",
        role_id=role.id,
        legacy_role="viewer",
        is_active=True,
        factory_id=factory.id,
    )
    db.add(user)
    await db.flush()

    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no="CAPA-D3-001",
        title="D3 Test CAPA",
        product_line_code="DC-DC-100",
        factory_id=factory.id,
        status="D3_INTERIM",
        severity="serious",
    )
    db.add(capa)
    await db.flush()
    await db.refresh(capa)

    return capa, user


async def _seed_d3_source_data(db: AsyncSession, factory_id: uuid.UUID, user_id: uuid.UUID, arrival_status: str = "signed", customer_code: str = "C1", supplier_no: str = "SUP-001", inspection_no: str = "IQC-001", ic_code: str = "IC-001"):
    """Seed the 4 source tables for a D3 import."""
    # ERP connection for inventory
    erp_conn = ERPConnection(
        connection_id=uuid.uuid4(),
        name="Test ERP",
        connector_type="mock",
        config={},
        factory_id=factory_id,
        created_by=user_id,
    )
    db.add(erp_conn)
    await db.flush()

    # Inventory balance
    inv = ERPInventoryBalance(
        balance_id=uuid.uuid4(),
        connection_id=erp_conn.connection_id,
        material_code="M1",
        location_code="LOC-A",
        lot_no="L1",
        quantity=100.0,
        unit="pcs",
        factory_id=factory_id,
    )
    db.add(inv)
    await db.flush()

    # Customer
    customer = Customer(
        customer_id=uuid.uuid4(),
        customer_code=customer_code,
        name="Acme",
        segment="key",
        factory_id=factory_id,
    )
    db.add(customer)
    await db.flush()

    # Shipment
    shipment = ERPShipment(
        erp_shipment_id=uuid.uuid4(),
        connection_id=erp_conn.connection_id,
        external_id="SH001",
        shipment_number="SH001",
        customer_code=customer_code,
        material_code="M1",
        lot_no="L1",
        quantity=30,
        factory_id=factory_id,
        erp_raw_data={"arrival_status": arrival_status, "unit": "pcs"},
    )
    db.add(shipment)
    await db.flush()

    # Supplier + IQC inspection
    supplier = Supplier(
        supplier_id=uuid.uuid4(),
        supplier_no=supplier_no,
        factory_id=factory_id,
        name="Test Supplier",
        short_name="TS",
        created_by=user_id,
    )
    db.add(supplier)
    await db.flush()

    iqc = IqcInspection(
        inspection_id=uuid.uuid4(),
        inspection_no=inspection_no,
        supplier_id=supplier.supplier_id,
        part_no="M1",
        lot_no="L1",
        lot_qty=200,
        defect_qty=5,
        defect_description="scratch",
        inspection_result="reject",
        factory_id=factory_id,
        product_line_code="DC-DC-100",
    )
    db.add(iqc)
    await db.flush()

    # Inspection characteristic + SPC alarm
    ic = InspectionCharacteristic(
        ic_id=uuid.uuid4(),
        ic_code=ic_code,
        product_line="DC-DC-100",
        factory_id=factory_id,
        process_name="Assy",
        characteristic_name="Dim",
        spec_upper=10.0,
        spec_lower=9.0,
        chart_type="xbar",
        created_by_id=user_id,
    )
    db.add(ic)
    await db.flush()

    alarm = SPCAlarm(
        alarm_id=uuid.uuid4(),
        ic_id=ic.ic_id,
        factory_id=factory_id,
        rule_no=1,
        severity="high",
        status="open",
        triggered_at=datetime.now(),
    )
    db.add(alarm)
    await db.flush()

    return erp_conn, customer, supplier


@pytest_asyncio.fixture
async def capa_d3_imported(db: AsyncSession, capa_d3_setup, monkeypatch):
    """Seed source data, run import, return (capa, run, user)."""
    capa, user = capa_d3_setup

    # Mock LLM so Transaction B succeeds during import.
    async def _build_client(db):
        return type("FakeClient", (), {"model": "test-model"})()

    monkeypatch.setattr(provider_adapter, "build_client", _build_client)
    monkeypatch.setattr(
        provider_adapter,
        "complete_json",
        AsyncMock(return_value={"risk_level": "medium", "risk_explanation": "ok"}),
    )

    await _seed_d3_source_data(db, capa.factory_id, user.user_id)

    result = await import_containment_data(db, capa.report_id, user, {})
    run = await db.get(CapaD3ImportRun, uuid.UUID(result["run_id"]))
    return capa, run, user


@pytest_asyncio.fixture
async def capa_d3_imported_huge(db: AsyncSession, capa_d3_setup, monkeypatch):
    """Like capa_d3_imported but with a snapshot payload > MAX_PROMPT_CHARS."""
    capa, user = capa_d3_setup

    async def _build_client(db):
        return type("FakeClient", (), {"model": "test-model"})()

    monkeypatch.setattr(provider_adapter, "build_client", _build_client)
    monkeypatch.setattr(
        provider_adapter,
        "complete_json",
        AsyncMock(return_value={"risk_level": "medium", "risk_explanation": "ok"}),
    )

    erp_conn, customer, supplier = await _seed_d3_source_data(
        db, capa.factory_id, user.user_id
    )

    # Create many inventory records to inflate the snapshot payload beyond 8k chars.
    for i in range(300):
        inv = ERPInventoryBalance(
            balance_id=uuid.uuid4(),
            connection_id=erp_conn.connection_id,
            material_code=f"M{i:04d}",
            location_code="LOC-A",
            lot_no=f"LOT-{i:04d}",
            quantity=1.0,
            unit="pcs",
            factory_id=capa.factory_id,
        )
        db.add(inv)
    await db.flush()

    result = await import_containment_data(db, capa.report_id, user, {})
    run = await db.get(CapaD3ImportRun, uuid.UUID(result["run_id"]))
    return capa, run, user


@pytest_asyncio.fixture
async def capa_d3_imported_unknown_arrival(db: AsyncSession, capa_d3_setup, monkeypatch):
    """Import with shipment arrival_status='unknown'."""
    capa, user = capa_d3_setup

    async def _build_client(db):
        return type("FakeClient", (), {"model": "test-model"})()

    monkeypatch.setattr(provider_adapter, "build_client", _build_client)
    monkeypatch.setattr(
        provider_adapter,
        "complete_json",
        AsyncMock(return_value={"risk_level": "low", "risk_explanation": "x"}),
    )

    await _seed_d3_source_data(
        db, capa.factory_id, user.user_id, arrival_status="unknown"
    )

    result = await import_containment_data(db, capa.report_id, user, {})
    run = await db.get(CapaD3ImportRun, uuid.UUID(result["run_id"]))
    return capa, run, user


@pytest_asyncio.fixture
async def capa_d3_imported_bad_mapping_version(db: AsyncSession, capa_d3_setup, monkeypatch):
    """Import with an unknown risk_mapping_version set after import."""
    capa, user = capa_d3_setup

    async def _build_client(db):
        return type("FakeClient", (), {"model": "test-model"})()

    monkeypatch.setattr(provider_adapter, "build_client", _build_client)
    monkeypatch.setattr(
        provider_adapter,
        "complete_json",
        AsyncMock(return_value={"risk_level": "medium", "risk_explanation": "ok"}),
    )

    await _seed_d3_source_data(db, capa.factory_id, user.user_id)

    result = await import_containment_data(db, capa.report_id, user, {})
    run = await db.get(CapaD3ImportRun, uuid.UUID(result["run_id"]))

    run.analysis_context = {
        **dict(run.analysis_context or {}),
        "risk_mapping_version": "v9",
    }
    await db.flush()

    return capa, run, user


@pytest_asyncio.fixture
async def superseded_run(db: AsyncSession, capa_d3_imported, monkeypatch):
    """Run a second import that demotes the first run to is_current=false."""
    capa, run, user = capa_d3_imported

    async def _build_client(db):
        return type("FakeClient", (), {"model": "test-model"})()

    monkeypatch.setattr(provider_adapter, "build_client", _build_client)
    monkeypatch.setattr(
        provider_adapter,
        "complete_json",
        AsyncMock(return_value={"risk_level": "medium", "risk_explanation": "ok"}),
    )

    await import_containment_data(db, capa.report_id, user, {})
    await db.refresh(run)
    return run


# ===== LLM mock fixtures =====


@pytest_asyncio.fixture
async def llm_mock(monkeypatch):
    """Patch provider_adapter.complete_json with a mutable AsyncMock."""
    async def _build_client(db):
        return type("FakeClient", (), {"model": "test-model"})()

    monkeypatch.setattr(provider_adapter, "build_client", _build_client)
    mock = AsyncMock()
    monkeypatch.setattr(provider_adapter, "complete_json", mock)
    return mock


@pytest_asyncio.fixture
async def llm_slow(monkeypatch):
    """Patch provider_adapter.complete_json with a mutable AsyncMock (test sets side_effect)."""
    async def _build_client(db):
        return type("FakeClient", (), {"model": "test-model"})()

    monkeypatch.setattr(provider_adapter, "build_client", _build_client)
    mock = AsyncMock()
    monkeypatch.setattr(provider_adapter, "complete_json", mock)
    return mock


@pytest_asyncio.fixture
async def llm_raise(monkeypatch):
    """Patch provider_adapter.complete_json with a mutable AsyncMock (test sets side_effect)."""
    async def _build_client(db):
        return type("FakeClient", (), {"model": "test-model"})()

    monkeypatch.setattr(provider_adapter, "build_client", _build_client)
    mock = AsyncMock()
    monkeypatch.setattr(provider_adapter, "complete_json", mock)
    return mock


@pytest_asyncio.fixture
async def llm_bad_schema(monkeypatch):
    """Patch provider_adapter.complete_json with a mutable AsyncMock (test sets return_value)."""
    async def _build_client(db):
        return type("FakeClient", (), {"model": "test-model"})()

    monkeypatch.setattr(provider_adapter, "build_client", _build_client)
    mock = AsyncMock()
    monkeypatch.setattr(provider_adapter, "complete_json", mock)
    return mock


@pytest_asyncio.fixture
async def no_creds(monkeypatch):
    """Patch provider_adapter.build_client to raise ProviderNotConfiguredError."""
    async def _raise(*args, **kwargs):
        raise ProviderNotConfiguredError("no cfg")

    monkeypatch.setattr(provider_adapter, "build_client", _raise)
    return _raise


# ===== Other fixtures =====


@pytest_asyncio.fixture
async def audit_reader(db: AsyncSession):
    """Return latest changed_fields for a capa + action."""
    async def _read(capa_id: uuid.UUID, action: str):
        result = await db.execute(
            select(AuditLog)
            .where(AuditLog.record_id == capa_id, AuditLog.action == action)
            .order_by(desc(AuditLog.operated_at))
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return row.changed_fields if row else {}

    return _read


@pytest_asyncio.fixture
async def stale_running_report(db: AsyncSession, capa_d3_imported):
    """Insert a stale running report row for the imported run."""
    capa, run, user = capa_d3_imported
    report = CapaD3ImpactReport(
        report_id=uuid.uuid4(),
        run_id=run.run_id,
        factory_id=run.factory_id,
        is_current=False,
        status="running",
        attempt_token=uuid.uuid4(),
        started_at=datetime.now(timezone.utc) - timedelta(seconds=300),
        generated_by=user.user_id,
        stage_runs=[],
        prompt_stats={},
        llm_available=False,
        batches=[],
        impact_qty=[],
        customer_impact=[],
        time_window={},
    )
    db.add(report)
    await db.flush()
    return report


@pytest_asyncio.fixture
async def customer_segment_changed():
    """No-op placeholder; tests update customers table inline."""
    return None


# ===== Advice generation fixtures (Task 7) =====


@pytest_asyncio.fixture
async def capa_d3_done_report(db: AsyncSession, capa_d3_imported):
    """Return (capa, report, run, user) with a done impact report."""
    capa, run, user = capa_d3_imported
    report = await db.scalar(
        select(CapaD3ImpactReport).where(
            CapaD3ImpactReport.run_id == run.run_id,
            CapaD3ImpactReport.is_current == True,
        )
    )
    return capa, report, run, user


@pytest_asyncio.fixture
async def capa_d3_two_shipment_batches_report(db: AsyncSession, capa_d3_setup, monkeypatch):
    """Create a CAPA with 2 shipment batches for batch-level trace tests."""
    capa, user = capa_d3_setup

    async def _build_client(db):
        return type("FakeClient", (), {"model": "test-model"})()

    monkeypatch.setattr(provider_adapter, "build_client", _build_client)
    monkeypatch.setattr(
        provider_adapter,
        "complete_json",
        AsyncMock(return_value={"risk_level": "medium", "risk_explanation": "ok"}),
    )

    # Seed source data with two shipments (different lot_no -> different batches)
    erp_conn = ERPConnection(
        connection_id=uuid.uuid4(),
        name="Test ERP",
        connector_type="mock",
        config={},
        factory_id=capa.factory_id,
        created_by=user.user_id,
    )
    db.add(erp_conn)
    await db.flush()

    # Inventory for both lots
    inv1 = ERPInventoryBalance(
        balance_id=uuid.uuid4(),
        connection_id=erp_conn.connection_id,
        material_code="M1",
        location_code="LOC-A",
        lot_no="L1",
        quantity=100.0,
        unit="pcs",
        factory_id=capa.factory_id,
    )
    inv2 = ERPInventoryBalance(
        balance_id=uuid.uuid4(),
        connection_id=erp_conn.connection_id,
        material_code="M1",
        location_code="LOC-B",
        lot_no="L2",
        quantity=50.0,
        unit="pcs",
        factory_id=capa.factory_id,
    )
    db.add(inv1)
    db.add(inv2)
    await db.flush()

    # Two customers
    customer1 = Customer(
        customer_id=uuid.uuid4(),
        customer_code="C1",
        name="Acme",
        segment="key",
        factory_id=capa.factory_id,
    )
    customer2 = Customer(
        customer_id=uuid.uuid4(),
        customer_code="C2",
        name="Beta",
        segment="normal",
        factory_id=capa.factory_id,
    )
    db.add(customer1)
    db.add(customer2)
    await db.flush()

    # Two shipments with different lot_no
    shipment1 = ERPShipment(
        erp_shipment_id=uuid.uuid4(),
        connection_id=erp_conn.connection_id,
        external_id="SH001",
        shipment_number="SH001",
        customer_code="C1",
        material_code="M1",
        lot_no="L1",
        quantity=30,
        factory_id=capa.factory_id,
        erp_raw_data={"arrival_status": "signed", "unit": "pcs"},
    )
    shipment2 = ERPShipment(
        erp_shipment_id=uuid.uuid4(),
        connection_id=erp_conn.connection_id,
        external_id="SH002",
        shipment_number="SH002",
        customer_code="C2",
        material_code="M1",
        lot_no="L2",
        quantity=20,
        factory_id=capa.factory_id,
        erp_raw_data={"arrival_status": "in_transit", "unit": "pcs"},
    )
    db.add(shipment1)
    db.add(shipment2)
    await db.flush()

    # Supplier + IQC
    supplier = Supplier(
        supplier_id=uuid.uuid4(),
        supplier_no="SUP-001",
        factory_id=capa.factory_id,
        name="Test Supplier",
        short_name="TS",
        created_by=user.user_id,
    )
    db.add(supplier)
    await db.flush()

    iqc = IqcInspection(
        inspection_id=uuid.uuid4(),
        inspection_no="IQC-001",
        supplier_id=supplier.supplier_id,
        part_no="M1",
        lot_no="L1",
        lot_qty=200,
        defect_qty=5,
        defect_description="scratch",
        inspection_result="reject",
        factory_id=capa.factory_id,
    )
    db.add(iqc)
    await db.flush()

    # SPC
    ic = InspectionCharacteristic(
        ic_id=uuid.uuid4(),
        ic_code="IC-001",
        product_line="DC-DC-100",
        factory_id=capa.factory_id,
        process_name="Assy",
        characteristic_name="Dim",
        spec_upper=10.0,
        spec_lower=9.0,
        chart_type="xbar",
        created_by_id=user.user_id,
    )
    db.add(ic)
    await db.flush()

    alarm = SPCAlarm(
        alarm_id=uuid.uuid4(),
        ic_id=ic.ic_id,
        factory_id=capa.factory_id,
        rule_no=1,
        severity="high",
        status="open",
        triggered_at=datetime.now(),
    )
    db.add(alarm)
    await db.flush()

    result = await import_containment_data(db, capa.report_id, user, {})
    run = await db.get(CapaD3ImportRun, uuid.UUID(result["run_id"]))
    report = await db.scalar(
        select(CapaD3ImpactReport).where(
            CapaD3ImpactReport.run_id == run.run_id,
            CapaD3ImpactReport.is_current == True,
        )
    )
    return capa, report, run, user


@pytest_asyncio.fixture
async def superseded_report(db: AsyncSession, capa_d3_done_report):
    """Mark the report as non-current (superseded by a concurrent re-import)."""
    capa, report, run, user = capa_d3_done_report
    report.is_current = False
    await db.flush()
    return report


@pytest_asyncio.fixture
async def stale_running_generation(db: AsyncSession, capa_d3_done_report):
    """Insert a stale running advice_generation row for the done report."""
    capa, report, run, user = capa_d3_done_report
    gen = CapaD3AdviceGeneration(
        generation_id=uuid.uuid4(),
        report_id=report.report_id,
        factory_id=report.factory_id,
        is_current=False,
        status="running",
        attempt_token=uuid.uuid4(),
        started_at=datetime.now(timezone.utc) - timedelta(seconds=300),
        generated_by=user.user_id,
        stage_runs=[],
        advice_count=0,
        rejected_advice_count=0,
        llm_available=False,
    )
    db.add(gen)
    await db.flush()
    return gen


# ===== Doc Gate fixtures (US-E2E-01.7) =====


@pytest_asyncio.fixture
async def capa_d8_gate(db: AsyncSession):
    """Create a CAPA in D8_GATE_PENDING status with factory + user (no docs)."""
    from app.models.factory import Factory
    from app.models.role import RoleDefinition
    from app.models.user import User
    factory = Factory(
        id=uuid.uuid4(), code="FAC-DOCG", name="DocGate Test Factory", is_active=True,
    )
    db.add(factory)
    await db.flush()
    role = RoleDefinition(
        id=uuid.uuid4(), role_key="test_role_docg", name_zh="测试角色",
        name_en="Test Role DocGate", description="Test role for doc-gate tests",
        is_system=False, is_editable=True, is_active=True,
    )
    db.add(role)
    await db.flush()
    user = User(
        user_id=uuid.uuid4(), username="test_docg_user", display_name="Test DocGate User",
        email="docg@example.com", password_hash="test_hash", role_id=role.id,
        legacy_role="quality_engineer", is_active=True, factory_id=factory.id,
    )
    db.add(user)
    await db.flush()
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no="CAPA-DOCG-001", title="DocGate Test CAPA",
        product_line_code="DC-DC-100", factory_id=factory.id, status="D8_GATE_PENDING",
        severity="serious", d4_root_cause="测试根因", d5_correction="永久措施",
        d7_prevention="预防复发", created_by=user.user_id,
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add(capa)
    await db.flush()
    await db.refresh(capa)
    return capa, user


@pytest_asyncio.fixture
async def capa_d8_gate_with_docs(db: AsyncSession, capa_d8_gate):
    """CAPA at D8_GATE_PENDING with a CP + FMEA (each with a baseline version)."""
    from app.models.fmea import FMEADocument
    from app.models.fmea_version import FMEAVersion
    capa, user = capa_d8_gate
    snapshot = {"nodes": [{"id": "node-1", "type": "ProcessStep", "name": "step1"}], "edges": []}
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no="PFMEA-DOCG-001", title="DocGate FMEA",
        fmea_type="PFMEA", product_line_code="DC-DC-100", factory_id=capa.factory_id,
        status="approved", graph_data=snapshot,
        created_by=user.user_id,
    )
    db.add(fmea)
    await db.flush()
    # Compute hash matching PG trigger (migration 020): encode(digest(snapshot::text,'sha256'),'hex')
    import json as _json
    import hashlib as _hashlib
    def _pg_jsonb_hash(snap):
        return _hashlib.sha256(_json.dumps(snap, sort_keys=True).encode("utf-8")).hexdigest()
    fmea_ver = FMEAVersion(
        version_id=uuid.uuid4(), fmea_id=fmea.fmea_id, factory_id=capa.factory_id,
        major_no=1, minor_no=0, snapshot=snapshot,
        sha256_hash=_pg_jsonb_hash(snapshot),
        change_type="approve", change_summary="initial", created_by=user.user_id,
        created_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    db.add(fmea_ver)
    capa.fmea_ref_id = fmea.fmea_id
    await db.flush()
    return capa, user


@pytest_asyncio.fixture
async def docg_no_creds(monkeypatch):
    """Patch provider_adapter.build_client to raise ProviderNotConfiguredError."""
    async def _raise(*args, **kwargs):
        raise ProviderNotConfiguredError("no cfg")
    monkeypatch.setattr(provider_adapter, "build_client", _raise)
    return _raise


@pytest_asyncio.fixture
async def docg_llm_mock(monkeypatch):
    """Patch provider_adapter build_client + complete_json with mutable AsyncMocks."""
    async def _build_client(db):
        return type("FakeClient", (), {"model": "test-model"})()
    monkeypatch.setattr(provider_adapter, "build_client", _build_client)
    mock = AsyncMock()
    monkeypatch.setattr(provider_adapter, "complete_json", mock)
    return mock


# ===== Doc-gate run_audit fixtures (Task 3) =====


def _pg_jsonb_hash(snapshot):
    import hashlib, json
    # PG JSONB::text uses compact separators + sorted keys (matches compute_snapshot_hash).
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


async def _make_done_analysis(db, capa, user, affected_docs):
    """Insert a done/is_current analysis row directly (bypass LLM)."""
    from app.services.capa_doc_gate_service import _build_allowlist, _compute_input_hash
    candidates = await _build_allowlist(db, capa)
    analysis = CapaDocgAnalysis(
        analysis_id=uuid.uuid4(), capa_id=capa.report_id, factory_id=capa.factory_id,
        is_current=True, status="done", affected_docs=affected_docs,
        analysis_input_hash=_compute_input_hash(capa, candidates),
        llm_available=True, model="test", completed_at=datetime.now(timezone.utc),
        generated_by=user.user_id,
    )
    db.add(analysis)
    await db.flush()
    return analysis


@pytest_asyncio.fixture
async def capa_with_done_analysis_no_bump(db, capa_d8_gate_with_docs):
    """CAPA + done analysis referencing the FMEA (modify node-1), but no new version after capa."""
    capa, user = capa_d8_gate_with_docs
    affected = [{
        "doc_type": "fmea", "doc_id": str(capa.fmea_ref_id), "doc_name": "DocGate FMEA",
        "baseline_version_id": None, "baseline_version": None,
        "key_points": [{"target_kind": "fmea_node", "expected_action": "modify",
                        "field": "prevention_control", "target_key": "node-1"}],
        "update_suggestion": "更新预防控制",
    }]
    await _make_done_analysis(db, capa, user, affected)
    return capa, user


@pytest_asyncio.fixture
async def capa_with_done_analysis_and_bumped_doc(db, capa_d8_gate_with_docs):
    """CAPA + done analysis + a NEW FMEA version (created after capa) that modifies node-1."""
    from sqlalchemy import text as _text
    from app.models.fmea import FMEADocument
    from app.models.fmea_version import FMEAVersion
    from app.services.version_service import get_latest_fmea_version
    capa, user = capa_d8_gate_with_docs
    fmea = await db.get(FMEADocument, capa.fmea_ref_id)
    # Baseline v1.0 (created before capa) — fetch its hash to populate affected_docs.baseline_version
    baseline_ver = await get_latest_fmea_version(db, fmea.fmea_id)
    baseline_version = {"major": baseline_ver.major_no, "minor": baseline_ver.minor_no, "sha256": baseline_ver.sha256_hash}
    # New v1.1 (after capa) modifying node-1
    new_snapshot = {"nodes": [{"id": "node-1", "type": "ProcessStep", "name": "step1", "prevention_control": "new-control"}], "edges": []}
    fmea.graph_data = new_snapshot
    vid = uuid.uuid4()
    import json as _json
    await db.execute(_text(
        "INSERT INTO fmea_versions (version_id, fmea_id, factory_id, major_no, minor_no, snapshot, sha256_hash, change_summary, change_type, created_by, created_at) "
        "VALUES (:vid, :fid, :fact, 1, 1, CAST(:snap AS JSONB), encode(digest(CAST(:snap AS JSONB)::text, 'sha256'), 'hex'), 'updated', 'minor', :uid, NOW())"
    ), {"vid": vid, "fid": fmea.fmea_id, "fact": capa.factory_id, "snap": _json.dumps(new_snapshot), "uid": user.user_id})
    await db.flush()
    affected = [{
        "doc_type": "fmea", "doc_id": str(capa.fmea_ref_id), "doc_name": "DocGate FMEA",
        "baseline_version_id": str(baseline_ver.version_id), "baseline_version": baseline_version,
        "key_points": [{"target_kind": "fmea_node", "expected_action": "modify",
                        "field": "prevention_control", "target_key": "node-1"}],
        "update_suggestion": "更新预防控制",
    }]
    await _make_done_analysis(db, capa, user, affected)
    return capa, user


@pytest_asyncio.fixture
async def capa_with_empty_done_analysis(db, capa_d8_gate_with_docs):
    """CAPA + done analysis with empty affected_docs (for confirm_no_affected path)."""
    capa, user = capa_d8_gate_with_docs
    await _make_done_analysis(db, capa, user, [])
    return capa, user


@pytest_asyncio.fixture
async def capa_with_cp_blocked_modify(db, capa_d8_gate):
    """CAPA at D8_GATE_PENDING + done analysis with CP modify target_key absent from latest.

    Baseline CP version has item_id='old-item'; latest has 'new-item' only →
    audit yields blocked (pending_update / uncovered modify). Used by structured
    waiver tests that require a real blocked_modify lineage break.
    """
    from datetime import timedelta
    from app.models.control_plan import ControlPlan
    from app.models.control_plan_version import ControlPlanVersion
    from app.services.version_service import compute_pg_jsonb_hash

    capa, user = capa_d8_gate
    cp = ControlPlan(
        cp_id=uuid.uuid4(),
        document_no=f"CP-WAIV-{uuid.uuid4().hex[:6]}",
        title="waiver cp",
        product_line_code=capa.product_line_code,
        factory_id=capa.factory_id,
        status="approved",
        created_by=user.user_id,
    )
    db.add(cp)
    await db.flush()

    async def _ins(items, major, minor, created_at):
        header = {}
        combined = {"header": header, "items": items}
        sha = await compute_pg_jsonb_hash(db, combined)
        ver = ControlPlanVersion(
            version_id=uuid.uuid4(),
            cp_id=cp.cp_id,
            factory_id=capa.factory_id,
            major_no=major,
            minor_no=minor,
            header_snapshot=header,
            items_snapshot=items,
            sha256_hash=sha,
            change_type="approve" if major == 1 and minor == 0 else "minor",
            change_summary="seed",
            created_by=user.user_id,
            created_at=created_at,
        )
        db.add(ver)
        await db.flush()
        return ver

    baseline_items = [{
        "item_id": "old-item",
        "source_fmea_node_id": "s1",
        "product_characteristic": "x",
        "control_method": "m-old",
    }]
    bver = await _ins(
        baseline_items, 1, 0,
        capa.created_at - timedelta(days=2),
    )
    # Latest rebuild: old-item gone, new-item present
    await _ins(
        [{"item_id": "new-item", "source_fmea_node_id": "s1",
          "product_characteristic": "x", "control_method": "m-new"}],
        1, 1, datetime.now(timezone.utc),
    )
    affected = [{
        "doc_type": "control_plan",
        "doc_id": str(cp.cp_id),
        "doc_name": cp.document_no,
        "baseline_version_id": str(bver.version_id),
        "baseline_version": {
            "major": bver.major_no, "minor": bver.minor_no, "sha256": bver.sha256_hash,
        },
        "key_points": [{
            "target_kind": "cp_item",
            "expected_action": "modify",
            "field": "control_method",
            "target_key": "old-item",
        }],
        "update_suggestion": "保留 item_id 后改 control_method",
    }]
    await _make_done_analysis(db, capa, user, affected)
    return capa, user, cp, "old-item", "control_method"
