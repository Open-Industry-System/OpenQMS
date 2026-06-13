"""
Unit and integration tests for MSA services and calculation engines.
"""
import pytest
import pytest_asyncio
import uuid
import os
import math
from datetime import datetime, date
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Ensure SECRET_KEY is set so app config doesn't throw
os.environ["SECRET_KEY"] = "test-secret-key-for-msa-service-integration-tests"

from tests.conftest import DEFAULT_FACTORY_ID
from app.database import Base
from app.config import settings
from app.models.user import User
from app.models.gauge import Gauge
from app.models.grr import GrrStudy, GrrMeasurement, GrrResult
from app.models.bias import BiasStudy, BiasMeasurement, BiasResult
from app.models.linearity import LinearityStudy, LinearityMeasurement, LinearityResult
from app.models.stability import StabilityStudy, StabilityMeasurement, StabilityResult
from app.models.attribute import AttributeStudy, AttributeMeasurement, AttributeResult

from app.services import (
    grr_engine,
    grr_service,
    bias_engine,
    bias_service,
    linearity_engine,
    linearity_service,
    stability_engine,
    stability_service,
    attribute_engine,
    attribute_service,
)

@pytest_asyncio.fixture
async def db_session():
    # Skip if database is not reachable
    from tests.conftest import _check_db_available
    if not await _check_db_available():
        pytest.skip("Database not available")
    from sqlalchemy.pool import NullPool
    from app.models.factory import Factory
    engine = create_async_engine(
        os.environ.get("TEST_DATABASE_URL", settings.DATABASE_URL),
        echo=False, poolclass=NullPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Ensure the default test factory exists (FK requirement)
        from sqlalchemy import select as _sel
        existing = (await session.execute(
            _sel(Factory).where(Factory.id == DEFAULT_FACTORY_ID)
        )).scalar_one_or_none()
        if existing is None:
            session.add(Factory(id=DEFAULT_FACTORY_ID, code="TEST", name="Test Factory"))
            await session.commit()
        yield session

    await engine.dispose()


# ─── 1. GRR ENGINE & SERVICE TESTS ──────────────────────────────────────────

def test_grr_engine_math():
    study = GrrStudy(
        study_id=uuid.uuid4(),
        study_no="GRR-2026-001",
        title="Test GRR Math",
        method="average_range",
        characteristic_name="Thickness",
        appraiser_count=2,
        part_count=2,
        trial_count=2,
        tolerance_upper=10.5,
        tolerance_lower=9.5,
    )
    
    # Construct repeatable, good measurements
    measurements = [
        # Appraiser A, Part 1: [10.0, 10.2]
        GrrMeasurement(appraiser_name="AppraiserA", part_no="Part1", trial_no=1, value=10.0),
        GrrMeasurement(appraiser_name="AppraiserA", part_no="Part1", trial_no=2, value=10.2),
        # Appraiser A, Part 2: [20.0, 20.1]
        GrrMeasurement(appraiser_name="AppraiserA", part_no="Part2", trial_no=1, value=20.0),
        GrrMeasurement(appraiser_name="AppraiserA", part_no="Part2", trial_no=2, value=20.1),
        # Appraiser B, Part 1: [10.1, 10.3]
        GrrMeasurement(appraiser_name="AppraiserB", part_no="Part1", trial_no=1, value=10.1),
        GrrMeasurement(appraiser_name="AppraiserB", part_no="Part1", trial_no=2, value=10.3),
        # Appraiser B, Part 2: [20.2, 20.0]
        GrrMeasurement(appraiser_name="AppraiserB", part_no="Part2", trial_no=1, value=20.2),
        GrrMeasurement(appraiser_name="AppraiserB", part_no="Part2", trial_no=2, value=20.0),
    ]
    
    result = grr_engine.compute_grr(study, measurements)
    
    assert result.study_id == study.study_id
    assert result.ev > 0
    assert result.av == 0.0  # Appraiser mean variance is smaller than trial spread, so it maxes to 0
    assert result.grr == result.ev
    assert result.pv > 0
    assert result.tv > 0
    assert result.ndc > 0
    assert result.conclusion in ["可接受", "条件接受", "不可接受"]


# ─── 2. BIAS ENGINE TESTS ───────────────────────────────────────────────────

def test_bias_engine_math():
    study = BiasStudy(
        study_id=uuid.uuid4(),
        study_no="BIAS-2026-001",
        title="Test Bias Math",
        reference_value=10.0,
        sample_size=10,
    )
    
    # 10 measurements with a mean of 10.14
    measurements = [
        BiasMeasurement(value=10.1, sequence_no=1),
        BiasMeasurement(value=10.2, sequence_no=2),
        BiasMeasurement(value=10.0, sequence_no=3),
        BiasMeasurement(value=10.3, sequence_no=4),
        BiasMeasurement(value=10.1, sequence_no=5),
        BiasMeasurement(value=10.2, sequence_no=6),
        BiasMeasurement(value=10.0, sequence_no=7),
        BiasMeasurement(value=10.2, sequence_no=8),
        BiasMeasurement(value=10.1, sequence_no=9),
        BiasMeasurement(value=10.2, sequence_no=10),
    ]
    
    result = bias_engine.compute_bias(study, measurements)
    
    assert result.study_id == study.study_id
    assert abs(result.mean - 10.14) < 0.001
    assert abs(result.bias - 0.14) < 0.001
    assert result.std_dev > 0
    assert result.t_statistic > 0
    assert 0 <= result.p_value <= 1


# ─── 3. LINEARITY ENGINE TESTS ──────────────────────────────────────────────

def test_linearity_engine_math():
    study = LinearityStudy(
        study_id=uuid.uuid4(),
        study_no="LIN-2026-001",
        title="Test Linearity Math",
        tolerance_upper=12.0,
        tolerance_lower=0.0,
    )
    
    measurements = [
        LinearityMeasurement(reference_value=2.0, measured_value=2.1, sequence_no=1),
        LinearityMeasurement(reference_value=4.0, measured_value=4.15, sequence_no=2),
        LinearityMeasurement(reference_value=6.0, measured_value=6.2, sequence_no=3),
        LinearityMeasurement(reference_value=8.0, measured_value=8.25, sequence_no=4),
        LinearityMeasurement(reference_value=10.0, measured_value=10.3, sequence_no=5),
    ]
    
    result = linearity_engine.compute_linearity(study, measurements)
    
    assert result.study_id == study.study_id
    assert abs(result.slope - 0.025) < 0.001
    assert abs(result.intercept - 0.05) < 0.001
    assert abs(result.r_squared - 1.0) < 0.01
    assert result.linearity > 0
    assert result.linearity_percent > 0


def test_stability_engine_math():
    study = StabilityStudy(
        study_id=uuid.uuid4(),
        study_no="STAB-2026-001",
        title="Test Stability Math",
        subgroup_size=5,
        reference_value=10.0,
    )
    
    measurements = [
        StabilityMeasurement(sample_mean=10.0, sample_range=0.5, sequence_no=1, measurement_date=date(2026, 5, 23)),
        StabilityMeasurement(sample_mean=10.1, sample_range=0.4, sequence_no=2, measurement_date=date(2026, 5, 24)),
        StabilityMeasurement(sample_mean=9.9, sample_range=0.6, sequence_no=3, measurement_date=date(2026, 5, 25)),
    ]
    
    result = stability_engine.compute_stability(study, measurements)
    
    assert result.study_id == study.study_id
    assert abs(result.cl_mean - 10.0) < 0.001
    assert abs(result.cl_range - 0.5) < 0.001
    assert result.ucl_mean > result.cl_mean
    assert result.lcl_mean < result.cl_mean
    assert result.ucl_range > result.cl_range
    assert result.cpk is not None


# ─── 5. ATTRIBUTE ENGINE TESTS ──────────────────────────────────────────────

def test_attribute_engine_math():
    study = AttributeStudy(
        study_id=uuid.uuid4(),
        study_no="ATTR-2026-001",
        title="Test Attribute Math",
    )
    
    measurements = [
        AttributeMeasurement(appraiser_name="AppraiserA", part_no="Part1", appraiser_decision="接受", known_standard="接受"),
        AttributeMeasurement(appraiser_name="AppraiserA", part_no="Part1", appraiser_decision="接受", known_standard="接受"),
        AttributeMeasurement(appraiser_name="AppraiserA", part_no="Part2", appraiser_decision="接受", known_standard="接受"),
        AttributeMeasurement(appraiser_name="AppraiserA", part_no="Part2", appraiser_decision="接受", known_standard="接受"),
        AttributeMeasurement(appraiser_name="AppraiserA", part_no="Part3", appraiser_decision="拒绝", known_standard="拒绝"),
        AttributeMeasurement(appraiser_name="AppraiserA", part_no="Part3", appraiser_decision="拒绝", known_standard="拒绝"),
        AttributeMeasurement(appraiser_name="AppraiserB", part_no="Part1", appraiser_decision="接受", known_standard="接受"),
        AttributeMeasurement(appraiser_name="AppraiserB", part_no="Part1", appraiser_decision="接受", known_standard="接受"),
        AttributeMeasurement(appraiser_name="AppraiserB", part_no="Part2", appraiser_decision="接受", known_standard="接受"),
        AttributeMeasurement(appraiser_name="AppraiserB", part_no="Part2", appraiser_decision="接受", known_standard="接受"),
        AttributeMeasurement(appraiser_name="AppraiserB", part_no="Part3", appraiser_decision="拒绝", known_standard="拒绝"),
        AttributeMeasurement(appraiser_name="AppraiserB", part_no="Part3", appraiser_decision="拒绝", known_standard="拒绝"),
    ]
    
    result = attribute_engine.compute_attribute(study, measurements)
    
    assert result.study_id == study.study_id
    assert result.effectiveness == 100.0
    assert result.miss_rate == 0.0
    assert result.false_alarm_rate == 0.0
    assert result.kappa_within == 1.0
    assert result.conclusion == "可接受"


# ─── 6. SERVICE INTEGRATION TESTS ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_msa_service_integration(db_session: AsyncSession):
    # Retrieve a seeded user for auditing/creation purposes
    user_result = await db_session.execute(select(User).limit(1))
    test_user = user_result.scalar_one_or_none()
    assert test_user is not None, "A user must be seeded in the DB to run MSA integration tests"
    user_id = test_user.user_id

    # 1. Create a Gauge
    gauge_no = f"GAUGE-{str(uuid.uuid4())[:8]}"
    gauge = Gauge(
        gauge_id=uuid.uuid4(),
        gauge_no=gauge_no,
        name="Digital Micrometer",
        model="Mitutoyo 293",
        manufacturer="Mitutoyo",
        resolution=0.001,
        measuring_range="0-25mm",
        department="Quality Dept",
        location="Lab 1",
        status="active",
        factory_id=DEFAULT_FACTORY_ID,
        created_by=user_id,
    )
    db_session.add(gauge)
    await db_session.commit()

    try:
        # 2. Test GRR Study Lifecycle via Service
        grr_study = await grr_service.create_study(
            db=db_session,
            title="Micrometer GRR",
            method="average_range",
            gauge_id=gauge.gauge_id,
            characteristic_name="Diameter",
            user_id=user_id,
            appraiser_count=2,
            part_count=2,
            trial_count=2,
            tolerance_upper=12.5,
            tolerance_lower=11.5,
        )
        assert grr_study.study_id is not None
        assert grr_study.study_no.startswith("GRR-")
        assert grr_study.status == "draft"

        # List studies
        studies, count = await grr_service.list_studies(db_session, gauge_id=gauge.gauge_id)
        assert count == 1
        assert studies[0].study_id == grr_study.study_id

        # Insert measurements
        meas_data = [
            {"appraiser_name": "A", "part_no": "P1", "trial_no": 1, "value": 12.01},
            {"appraiser_name": "A", "part_no": "P1", "trial_no": 2, "value": 12.02},
            {"appraiser_name": "A", "part_no": "P2", "trial_no": 1, "value": 12.10},
            {"appraiser_name": "A", "part_no": "P2", "trial_no": 2, "value": 12.11},
            {"appraiser_name": "B", "part_no": "P1", "trial_no": 1, "value": 12.01},
            {"appraiser_name": "B", "part_no": "P1", "trial_no": 2, "value": 12.03},
            {"appraiser_name": "B", "part_no": "P2", "trial_no": 1, "value": 12.12},
            {"appraiser_name": "B", "part_no": "P2", "trial_no": 2, "value": 12.10},
        ]
        await grr_service.upsert_measurements(db_session, grr_study.study_id, meas_data)

        # Retrieve measurements
        measurements = await grr_service.get_measurements(db_session, grr_study.study_id)
        assert len(measurements) == 8

        # Compute results
        res = grr_engine.compute_grr(grr_study, measurements)
        saved_res = await grr_service.save_result(db_session, res)
        assert saved_res.study_id == grr_study.study_id
        assert saved_res.grr > 0

        # Complete study
        completed_study = await grr_service.complete_study(db_session, grr_study, user_id, accepted=True)
        assert completed_study.status == "completed"
        assert completed_study.accepted_by == user_id

        # Cleanup study & results
        await db_session.execute(delete(GrrResult).where(GrrResult.study_id == grr_study.study_id))
        await db_session.execute(delete(GrrMeasurement).where(GrrMeasurement.study_id == grr_study.study_id))
        await db_session.execute(delete(GrrStudy).where(GrrStudy.study_id == grr_study.study_id))
        await db_session.commit()

    finally:
        # Cleanup gauge
        await db_session.execute(delete(Gauge).where(Gauge.gauge_id == gauge.gauge_id))
        await db_session.commit()
