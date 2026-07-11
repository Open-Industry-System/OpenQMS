"""Tests for D3 advice adoption service and API (US-E2E-01.1 Task 9)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.capa_d3 import (
    CapaD3AdviceAdoption,
    CapaD3AdviceGeneration,
    CapaD3AiAdvice,
    CapaD3ImpactReport,
    CapaD3ImportRun,
)
from app.models.factory import Factory
from app.models.user import User
from app.services.capa_d3_containment_service import adopt_advice, generate_advice
from tests.capa.conftest import _seed_d3_source_data

pytestmark = pytest.mark.requires_db


# ===== Fixtures for adoption tests =====


@pytest_asyncio.fixture
async def capa_d3_with_current_advice(
    db: AsyncSession, capa_d3_done_report, llm_mock
):
    """CAPA with current advice generation + at least one advice. Returns (capa, advice, user)."""
    capa, report, run, user = capa_d3_done_report
    # Generate advice
    llm_mock.return_value = {
        "advice": [
            {
                "advice_type": "strict_inspection",
                "advice_text": "加强检验",
                "target_batch_refs": None,
                "provenance_sources_hint": ["iqc"],
            }
        ]
    }
    result = await generate_advice(db, capa.report_id, report.report_id, user, None)
    assert result["status"] == "done", f"Advice generation should succeed, got {result}"
    await db.commit()

    # Fetch the advice
    current_gen = await db.scalar(
        select(CapaD3AdviceGeneration).where(
            CapaD3AdviceGeneration.report_id == report.report_id,
            CapaD3AdviceGeneration.is_current == True,
        )
    )
    assert current_gen is not None, "Current generation should exist after generate_advice"
    advice = await db.scalar(
        select(CapaD3AiAdvice).where(
            CapaD3AiAdvice.generation_id == current_gen.generation_id
        )
    )
    assert advice is not None, "Advice should exist in current generation"
    return capa, advice, user


@pytest_asyncio.fixture
async def capa_d3_with_old_and_current_advice(
    db: AsyncSession, capa_d3_done_report, llm_mock
):
    """Two generations, old demoted, with advice in each. Returns (capa, old_advice, current_advice, user)."""
    capa, report, run, user = capa_d3_done_report

    # Generate old advice - use strict_inspection which doesn't need batch refs
    llm_mock.return_value = {
        "advice": [
            {
                "advice_type": "strict_inspection",
                "advice_text": "加强检验",
                "target_batch_refs": None,
                "provenance_sources_hint": ["iqc"],
            }
        ]
    }
    result1 = await generate_advice(db, capa.report_id, report.report_id, user, None)
    assert result1["status"] == "done", f"First advice generation should succeed, got {result1}"
    await db.commit()

    old_gen = await db.scalar(
        select(CapaD3AdviceGeneration)
        .where(CapaD3AdviceGeneration.report_id == report.report_id)
        .order_by(CapaD3AdviceGeneration.created_at.desc())
        .limit(1)
    )
    assert old_gen is not None, "Old generation should exist after first generate_advice"
    old_advice = await db.scalar(
        select(CapaD3AiAdvice).where(
            CapaD3AiAdvice.generation_id == old_gen.generation_id
        )
    )
    assert old_advice is not None, "Old advice should exist in old generation"

    # Generate new advice (demotes old)
    llm_mock.return_value = {
        "advice": [
            {
                "advice_type": "strict_inspection",
                "advice_text": "加强检验",
                "target_batch_refs": None,
                "provenance_sources_hint": ["iqc"],
            }
        ]
    }
    result2 = await generate_advice(db, capa.report_id, report.report_id, user, None)
    assert result2["status"] == "done", f"Second advice generation should succeed, got {result2}"
    await db.commit()

    current_gen = await db.scalar(
        select(CapaD3AdviceGeneration).where(
            CapaD3AdviceGeneration.report_id == report.report_id,
            CapaD3AdviceGeneration.is_current == True,
        )
    )
    assert current_gen is not None, "Current generation should exist after second generate_advice"
    current_advice = await db.scalar(
        select(CapaD3AiAdvice).where(
            CapaD3AiAdvice.generation_id == current_gen.generation_id
        )
    )
    assert current_advice is not None, "Current advice should exist in current generation"

    return capa, old_advice, current_advice, user


@pytest_asyncio.fixture
async def two_capas_same_factory_with_advice(
    db: AsyncSession, capa_d3_done_report, llm_mock
):
    """Two CAPAs in same factory, each with advice. Returns (capa_a, advice_a, capa_b, user)."""
    capa_a, report_a, run_a, user = capa_d3_done_report

    # Generate advice for capa_a
    llm_mock.return_value = {
        "advice": [
            {
                "advice_type": "strict_inspection",
                "advice_text": "加强检验",
                "target_batch_refs": None,
                "provenance_sources_hint": ["iqc"],
            }
        ]
    }
    result_a = await generate_advice(db, capa_a.report_id, report_a.report_id, user, None)
    assert result_a["status"] == "done", f"Advice generation for capa_a should succeed, got {result_a}"
    await db.commit()

    current_gen_a = await db.scalar(
        select(CapaD3AdviceGeneration).where(
            CapaD3AdviceGeneration.report_id == report_a.report_id,
            CapaD3AdviceGeneration.is_current == True,
        )
    )
    assert current_gen_a is not None, "Current generation for capa_a should exist"
    advice_a = await db.scalar(
        select(CapaD3AiAdvice).where(
            CapaD3AiAdvice.generation_id == current_gen_a.generation_id
        )
    )
    assert advice_a is not None, "Advice for capa_a should exist"

    # Create capa_b in the same factory
    capa_b = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no="CAPA-D3-002",
        title="D3 Test CAPA B",
        product_line_code="DC-DC-100",
        factory_id=capa_a.factory_id,
        status="D3_INTERIM",
        severity="serious",
    )
    db.add(capa_b)
    await db.flush()
    await db.commit()

    # Import for capa_b - use different codes to avoid UQ violations
    from app.services.capa_d3_containment_service import import_containment_data

    await _seed_d3_source_data(
        db, capa_b.factory_id, user.user_id,
        customer_code="C2", supplier_no="SUP-002", inspection_no="IQC-002", ic_code="IC-002"
    )

    # Mock LLM for report generation to succeed
    llm_mock.return_value = {"risk_level": "medium", "risk_explanation": "ok"}
    result = await import_containment_data(db, capa_b.report_id, user, {})
    run_b = await db.get(CapaD3ImportRun, uuid.UUID(result["run_id"]))
    assert run_b is not None, f"Run B should be created, result={result}"
    assert result["report_status"] == "done", f"Report B should be done, got {result}"

    report_b = await db.scalar(
        select(CapaD3ImpactReport).where(
            CapaD3ImpactReport.run_id == run_b.run_id,
            CapaD3ImpactReport.is_current == True,
        )
    )
    assert report_b is not None, f"Report B should be created after successful import"

    # Generate advice for capa_b - use iqc which doesn't need batch refs
    llm_mock.return_value = {
        "advice": [
            {
                "advice_type": "strict_inspection",
                "advice_text": "加强检验",
                "target_batch_refs": None,
                "provenance_sources_hint": ["iqc"],
            }
        ]
    }
    result_b = await generate_advice(db, capa_b.report_id, report_b.report_id, user, None)
    assert result_b["status"] == "done", f"Advice generation for capa_b should succeed, got {result_b}"
    await db.commit()

    return capa_a, advice_a, capa_b, user


@pytest_asyncio.fixture
async def capa_d3_with_adopted(db: AsyncSession, capa_d3_with_current_advice):
    """CAPA with an adopted advice. Returns (capa, adoption)."""
    capa, advice, user = capa_d3_with_current_advice
    adoption = CapaD3AdviceAdoption(
        adoption_id=uuid.uuid4(),
        advice_id=advice.advice_id,
        factory_id=advice.factory_id,
        decision="adopted",
        adopted_text="已隔离批次 A",
        advice_type=advice.advice_type,
        source_provenance=advice.source_provenance,
        decided_by=user.user_id,
        decided_at=datetime.now(timezone.utc),
    )
    db.add(adoption)
    await db.flush()
    return capa, adoption


@pytest_asyncio.fixture
async def e2e_user_id(db: AsyncSession, capa_d3_with_current_advice):
    """Real user UUID for migration-level UQ tests."""
    capa, advice, user = capa_d3_with_current_advice
    return user.user_id


@pytest_asyncio.fixture
async def mig_db_url(db: AsyncSession):
    """Sync engine URL for raw SQL tests."""
    from app.config import settings

    return settings.DATABASE_URL.replace("+asyncpg", "")


# ===== Service tests =====


async def test_adopt_inserts_only_advice_id(db: AsyncSession, capa_d3_with_current_advice):
    capa, advice, user = capa_d3_with_current_advice
    result = await adopt_advice(
        db, capa.report_id, advice.advice_id, "adopted", "隔离批次 A", user
    )
    await db.commit()
    adoption = (
        await db.execute(
            select(CapaD3AdviceAdoption).where(
                CapaD3AdviceAdoption.advice_id == advice.advice_id
            )
        )
    ).scalar_one()
    assert adoption.decision == "adopted" and adoption.adopted_text == "隔离批次 A"
    assert adoption.advice_id == advice.advice_id  # 不存 report_id/generation_id


async def test_adopt_uq_single_decision_rejects_second(
    db: AsyncSession, capa_d3_with_current_advice, e2e_user_id
):
    """Test that UQ constraint prevents second adoption for same advice_id."""
    capa, advice, user = capa_d3_with_current_advice
    # Test the UQ constraint at the service level by inserting via raw SQL through db
    from sqlalchemy import text

    # Insert first adoption
    await db.execute(
        text(
            "INSERT INTO capa_d3_advice_adoption (adoption_id,advice_id,factory_id,decision,adopted_text,advice_type,source_provenance,decided_by,decided_at,created_at) "
            "VALUES (gen_random_uuid(),:adv,:fac,'adopted','t1','recall','[]',:uid,now(),now())"
        ),
        {"adv": str(advice.advice_id), "fac": str(advice.factory_id), "uid": str(e2e_user_id)},
    )
    await db.commit()

    # Second insert should fail with IntegrityError (service catches it for rejected, but we test raw SQL)
    with pytest.raises(IntegrityError):
        await db.execute(
            text(
                "INSERT INTO capa_d3_advice_adoption (adoption_id,advice_id,factory_id,decision,adopted_text,advice_type,source_provenance,decided_by,decided_at,created_at) "
                "VALUES (gen_random_uuid(),:adv,:fac,'adopted','t2','recall','[]',:uid,now(),now())"
            ),
            {"adv": str(advice.advice_id), "fac": str(advice.factory_id), "uid": str(e2e_user_id)},
        )
        await db.commit()


async def test_adopt_same_decision_diff_text_updates(
    db: AsyncSession, capa_d3_with_current_advice, audit_reader
):
    capa, advice, user = capa_d3_with_current_advice
    r1 = await adopt_advice(
        db, capa.report_id, advice.advice_id, "adopted", "t1", user
    )
    await db.commit()
    r2 = await adopt_advice(
        db, capa.report_id, advice.advice_id, "adopted", "t2-different", user
    )
    await db.commit()
    assert r1["adoption_id"] == r2["adoption_id"]
    changed = await audit_reader(capa.report_id, "D3_ADVICE_DECISION_CHANGED")
    assert changed["old_adopted_text"] == "t1" and changed["new_adopted_text"] == "t2-different"


async def test_adopt_idempotent_same_decision_text(db: AsyncSession, capa_d3_with_current_advice):
    capa, advice, user = capa_d3_with_current_advice
    r1 = await adopt_advice(db, capa.report_id, advice.advice_id, "rejected", None, user)
    await db.commit()
    r2 = await adopt_advice(db, capa.report_id, advice.advice_id, "rejected", None, user)
    await db.commit()
    assert r1["adoption_id"] == r2["adoption_id"]


async def test_adopt_change_decision_writes_decision_changed_audit(
    db: AsyncSession, capa_d3_with_current_advice, audit_reader
):
    capa, advice, user = capa_d3_with_current_advice
    await adopt_advice(db, capa.report_id, advice.advice_id, "adopted", "t1", user)
    await db.commit()
    await adopt_advice(db, capa.report_id, advice.advice_id, "rejected", None, user)
    await db.commit()
    changed = await audit_reader(capa.report_id, "D3_ADVICE_DECISION_CHANGED")
    assert changed["old_decision"] == "adopted" and changed["new_decision"] == "rejected"


async def test_adopt_check_rejected_requires_null_text(db: AsyncSession, capa_d3_with_current_advice):
    capa, advice, user = capa_d3_with_current_advice
    with pytest.raises(IntegrityError):
        await adopt_advice(
            db, capa.report_id, advice.advice_id, "rejected", "should be null", user
        )
        await db.commit()


async def test_adopt_cross_generation_advice_rejected(
    db: AsyncSession, capa_d3_with_old_and_current_advice
):
    capa, old_advice, _current_advice, user = capa_d3_with_old_and_current_advice
    with pytest.raises(ValueError, match="建议不属于当前 generation"):
        await adopt_advice(db, capa.report_id, old_advice.advice_id, "adopted", "t", user)
        await db.commit()


async def test_adopt_cross_capa_same_factory_404(
    db: AsyncSession, two_capas_same_factory_with_advice
):
    capa_a, advice_a, capa_b, user = two_capas_same_factory_with_advice
    with pytest.raises(LookupError, match="建议不属于该 CAPA"):
        await adopt_advice(db, capa_b.report_id, advice_a.advice_id, "adopted", "t", user)
        await db.commit()


async def test_adopt_cross_factory_404(db: AsyncSession, two_capas_same_factory_with_advice):
    """Test cross-factory rejection."""
    capa_a, advice_a, capa_b, user = two_capas_same_factory_with_advice
    # Create a different factory
    other_factory = Factory(
        id=uuid.uuid4(),
        code="OTHER-FAC",
        name="Other Factory",
        is_active=True,
    )
    db.add(other_factory)
    await db.flush()
    await db.commit()

    # Change capa_b's factory to different factory (FK violation expected)
    # Instead of changing factory_id (FK violation), test with advice from different factory
    # by creating a new CAPA in a different factory
    from app.services.capa_d3_containment_service import import_containment_data

    capa_c = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no="CAPA-D3-003",
        title="D3 Test CAPA C",
        product_line_code="DC-DC-100",
        factory_id=other_factory.id,
        status="D3_INTERIM",
        severity="serious",
    )
    db.add(capa_c)
    await db.flush()
    await db.commit()

    # Import for capa_c
    await _seed_d3_source_data(
        db, capa_c.factory_id, user.user_id,
        customer_code="C3", supplier_no="SUP-003", inspection_no="IQC-003", ic_code="IC-003"
    )

    # Capa_c doesn't have advice yet, so trying to adopt advice_a on capa_c should fail
    with pytest.raises(LookupError, match="建议不属于该 CAPA"):
        await adopt_advice(db, capa_c.report_id, advice_a.advice_id, "adopted", "t", user)
        await db.commit()