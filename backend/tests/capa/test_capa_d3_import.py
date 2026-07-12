"""Tests for D3 Containment Import Service (US-E2E-01.1 Task 2+4).

Unit tests for core service functions plus integration tests for Transaction B.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capa_d3 import CapaD3ImportRun, CapaD3ContainmentSnapshot
from app.models.capa import CAPAEightD
from app.models.factory import Factory
from app.models.user import User
from app.models.role import RoleDefinition
from app.services.agent import provider_adapter
from app.services.agent.provider_adapter import ProviderNotConfiguredError
from app.services.capa_d3_containment_service import import_containment_data
from app.services.capa_d3_risk_mappings import get_risk_floor, CURRENT_RISK_MAPPING_VERSION


# ===== Risk Mapping Tests =====

def test_risk_floor_mapping_v1():
    """Test risk floor mapping for v1."""
    floor, error = get_risk_floor("serious", "v1")
    assert floor == "medium"
    assert error is None


def test_risk_floor_critical_maps_to_high():
    """Critical and fatal both map to high."""
    floor, _ = get_risk_floor("critical", "v1")
    assert floor == "high"
    floor, _ = get_risk_floor("fatal", "v1")
    assert floor == "high"


def test_risk_floor_unknown_version_returns_error():
    """Unknown version returns error code."""
    floor, error = get_risk_floor("serious", "unknown_version")
    assert floor is None
    assert error == "unknown_risk_mapping_version"


# ===== Import Service Tests =====

@pytest.fixture
async def db_role(db: AsyncSession) -> RoleDefinition:
    """Create a test role for user FK."""
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
    await db.commit()
    await db.refresh(role)
    return role


@pytest.fixture
async def db_user(db: AsyncSession, db_role: RoleDefinition) -> User:
    """Create a test user."""
    user = User(
        user_id=uuid.uuid4(),
        username="test_d3_user",
        display_name="Test D3 User",
        email="test@example.com",
        password_hash="test_hash",
        role_id=db_role.id,
        legacy_role="viewer",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def db_factory(db: AsyncSession) -> Factory:
    """Create a test factory."""
    factory = Factory(
        id=uuid.uuid4(),
        code="FAC-D3",
        name="D3 Test Factory",
        is_active=True,
    )
    db.add(factory)
    await db.commit()
    await db.refresh(factory)
    return factory


@pytest.fixture
async def db_capa(db: AsyncSession, db_factory: Factory) -> CAPAEightD:
    """Create a test CAPA in D3_INTERIM status."""
    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no="CAPA-D3-001",
        title="D3 Test CAPA",
        product_line_code="DC-DC-100",
        factory_id=db_factory.id,
        status="D3_INTERIM",
        severity="serious",
    )
    db.add(capa)
    await db.commit()
    await db.refresh(capa)
    return capa


async def test_import_creates_run_with_4_snapshots(
    db: AsyncSession, db_user: User, db_factory: Factory, db_capa: CAPAEightD, audit_reader
):
    """Import creates a run with 4 snapshots (empty payload for missing sources)."""
    result = await import_containment_data(db, db_capa.report_id, db_user, {})

    assert "run_id" in result
    assert len(result["snapshots"]) == 4

    snapshot_types = {s["snapshot_type"] for s in result["snapshots"]}
    assert snapshot_types == {"inventory", "shipment", "iqc", "spc"}

    # Verify run is current and completed
    run = await db.get(CapaD3ImportRun, uuid.UUID(result["run_id"]))
    assert run is not None
    assert run.is_current is True
    assert run.status == "completed"
    assert run.completed_at is not None
    assert run.analysis_context == {
        "capa_severity": "serious",
        "risk_mapping_version": CURRENT_RISK_MAPPING_VERSION,
    }

    # Verify D3_DATA_IMPORTED audit is written before Transaction B
    audit_fields = await audit_reader(db_capa.report_id, "D3_DATA_IMPORTED")
    assert audit_fields["run_id"] == result["run_id"]
    assert audit_fields["snapshot_count"] == len(result["snapshots"])
    assert "report_status" in audit_fields


async def test_new_run_demotes_old_current(
    db: AsyncSession, db_user: User, db_factory: Factory, db_capa: CAPAEightD
):
    """New run demotes old current run without partial UQ clash."""
    # First import creates run 1
    result1 = await import_containment_data(db, db_capa.report_id, db_user, {})
    run1_id = uuid.UUID(result1["run_id"])

    # Verify first run is current
    run1 = await db.get(CapaD3ImportRun, run1_id)
    assert run1.is_current is True

    # Second import creates run 2, demotes run 1
    result2 = await import_containment_data(db, db_capa.report_id, db_user, {})
    run2_id = uuid.UUID(result2["run_id"])

    # Refresh run1
    await db.refresh(run1)

    # Verify run1 demoted, run2 current
    assert run1.is_current is False
    run2 = await db.get(CapaD3ImportRun, run2_id)
    assert run2.is_current is True


async def test_empty_source_persists_zero_count(
    db: AsyncSession, db_user: User, db_factory: Factory, db_capa: CAPAEightD
):
    """Empty SPC source persists zero count."""
    result = await import_containment_data(db, db_capa.report_id, db_user, {})

    spc = next(s for s in result["snapshots"] if s["snapshot_type"] == "spc")
    assert spc["record_count"] == 0

    snap = await db.get(CapaD3ContainmentSnapshot, uuid.UUID(spc["snapshot_id"]))
    assert snap.payload == []


async def test_sequential_imports_create_two_runs_with_one_current(
    db: AsyncSession, db_user: User, db_factory: Factory, db_capa: CAPAEightD
):
    """Sequential imports create two runs with one current."""
    # Run first import
    result1 = await import_containment_data(db, db_capa.report_id, db_user, {})
    run1_id = uuid.UUID(result1["run_id"])

    # Run second import
    result2 = await import_containment_data(db, db_capa.report_id, db_user, {})
    run2_id = uuid.UUID(result2["run_id"])

    # Get all runs for this CAPA
    result = await db.execute(
        select(CapaD3ImportRun)
        .where(CapaD3ImportRun.capa_id == db_capa.report_id)
        .order_by(CapaD3ImportRun.created_at)
    )
    runs = result.scalars().all()

    # Should have exactly 2 runs
    assert len(runs) == 2

    # Exactly one should be current
    current_count = sum(1 for r in runs if r.is_current)
    assert current_count == 1

    # The second run should be current
    run1 = next(r for r in runs if r.run_id == run1_id)
    run2 = next(r for r in runs if r.run_id == run2_id)
    assert run1.is_current is False
    assert run2.is_current is True


# ===== Transaction B Tests (Task 4) =====


@pytest.mark.asyncio
async def test_import_transaction_b_does_not_rollback_a_on_failure(
    db: AsyncSession, capa_d3_setup, monkeypatch
):
    capa, user = capa_d3_setup
    async def _build_client(db):
        return type("FakeClient", (), {"model": "test-model"})()
    monkeypatch.setattr(provider_adapter, "build_client", _build_client)
    monkeypatch.setattr(
        provider_adapter,
        "complete_json",
        AsyncMock(side_effect=RuntimeError("LLM down")),
    )
    result = await import_containment_data(db, capa.report_id, user, {})
    assert result["report_status"] == "failed"
    run = await db.get(CapaD3ImportRun, uuid.UUID(result["run_id"]))
    assert run.is_current is True and run.status == "completed"
    snaps = (
        await db.execute(
            select(CapaD3ContainmentSnapshot).where(
                CapaD3ContainmentSnapshot.run_id == result["run_id"]
            )
        )
    ).scalars().all()
    assert len(snaps) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("behavior", ["ok", "fail", "no_creds"])
async def test_import_report_status_only_done_failed_blocked_superseded(
    db: AsyncSession, capa_d3_setup, monkeypatch, behavior
):
    capa, user = capa_d3_setup
    if behavior == "ok":
        fake_client = type("FakeClient", (), {"model": "test-model"})()
        monkeypatch.setattr(provider_adapter, "build_client", lambda db: fake_client)
        monkeypatch.setattr(
            provider_adapter,
            "complete_json",
            AsyncMock(return_value={"risk_level": "low", "risk_explanation": "x"}),
        )
    elif behavior == "fail":
        fake_client = type("FakeClient", (), {"model": "test-model"})()
        monkeypatch.setattr(provider_adapter, "build_client", lambda db: fake_client)
        monkeypatch.setattr(
            provider_adapter,
            "complete_json",
            AsyncMock(side_effect=RuntimeError("LLM down")),
        )
    else:  # no_creds
        async def _raise(*args, **kwargs):
            raise ProviderNotConfiguredError("no cfg")
        monkeypatch.setattr(provider_adapter, "build_client", _raise)

    result = await import_containment_data(db, capa.report_id, user, {})
    assert result["report_status"] in {"done", "failed", "blocked", "superseded"}
