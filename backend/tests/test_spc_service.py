import pytest
import pytest_asyncio
import uuid
import os
import math
from datetime import datetime, timezone
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Ensure SECRET_KEY is set so app config doesn't throw
os.environ["SECRET_KEY"] = "test-secret-key-for-spc-service-integration-tests"

from tests.conftest import DEFAULT_FACTORY_ID
from app.database import Base
from app.config import settings
from app.models.user import User
from app.models.spc import InspectionCharacteristic, SampleBatch, SPCAlarm, ControlLimitSnapshot
from app.services.spc_service import (
    create_inspection_characteristic,
    list_inspection_characteristics,
    add_sample_batch,
    get_chart_data,
    lock_unlock_control_limits,
    list_snapshots,
    activate_snapshot,
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

@pytest.mark.asyncio
async def test_spc_v1_1_lifecycle(db_session: AsyncSession):
    # 1. Fetch a valid user_id from the database
    user_result = await db_session.execute(select(User).limit(1))
    test_user = user_result.scalar_one_or_none()
    assert test_user is not None, "A user must be seeded in the DB to run SPC integration tests"
    user_id = test_user.user_id

    # Track all created characteristic IDs for clean-up
    created_ic_ids = []

    try:
        # 2. Create a P-chart (proportion nonconforming, variable limits)
        process_suffix = f"Test-{str(uuid.uuid4())[:8]}"
        ic_data = {
            "product_line": "DC-DC-100",
            "process_name": f"SMT-{process_suffix}",
            "characteristic_name": "DefectRate",
            "spec_upper": 0.15,
            "spec_lower": 0.0,
            "target_value": 0.02,
            "chart_type": "p",
            "subgroup_size": 1,
            "rules_config": {
                "rule_1": True,
                "rule_2": False,
            }
        }
        ic = await create_inspection_characteristic(db_session, user_id, ic_data, factory_id=DEFAULT_FACTORY_ID)
        assert ic.ic_id is not None
        created_ic_ids.append(ic.ic_id)
        assert ic.chart_type == "p"
        assert ic.control_limits_locked is False

        # 3. Add initial batches to enable limit calculation
        # Let's add 2 batches (defect rates 0.05 and 0.03)
        batch1 = await add_sample_batch(db_session, user_id, ic.ic_id, {
            "batch_no": "B001",
            "sampled_at": "2026-05-22T10:00:00",
            "inspected_count": 100,
            "defect_count": 5,
        })
        assert batch1.batch_id is not None

        batch2 = await add_sample_batch(db_session, user_id, ic.ic_id, {
            "batch_no": "B002",
            "sampled_at": "2026-05-22T11:00:00",
            "inspected_count": 200,
            "defect_count": 6,
        })
        assert batch2.batch_id is not None

        # Verify dynamic control limits are computed and fetched correctly
        chart_data = await get_chart_data(db_session, ic.ic_id)
        assert chart_data["chart_type"] == "p"
        assert len(chart_data["data_points"]) == 2
        
        limits = chart_data["limits"]
        assert limits["cl"] is not None
        assert "ucl_list" in limits
        assert "lcl_list" in limits
        assert len(limits["ucl_list"]) == 2
        
        # Verify alarm check works correctly (0.05 and 0.03 defect rate)
        # Average rate = (5 + 6) / (100 + 200) = 11 / 300 = 0.0367
        assert abs(limits["cl"] - 0.0367) < 0.001

        # 4. Lock control limits (should generate Snapshot version 1)
        ic_locked = await lock_unlock_control_limits(db_session, user_id, ic.ic_id, True)
        assert ic_locked.control_limits_locked is True

        snapshots = await list_snapshots(db_session, ic.ic_id)
        assert len(snapshots) == 1
        v1_snapshot = snapshots[0]
        assert v1_snapshot.version_no == 1
        assert v1_snapshot.is_locked is True
        assert v1_snapshot.is_active is True
        assert abs(float(v1_snapshot.cl) - 0.0367) < 0.001

        # 5. Add a 3rd batch when locked
        # Verify it uses the locked historical CL (0.0367) for calculating its variable limits
        batch3 = await add_sample_batch(db_session, user_id, ic.ic_id, {
            "batch_no": "B003",
            "sampled_at": "2026-05-22T12:00:00",
            "inspected_count": 100,
            "defect_count": 25,  # 25% defect rate, definitely triggers alarm
        })
        assert batch3.batch_id is not None

        # Check chart data again
        chart_data_locked = await get_chart_data(db_session, ic.ic_id)
        assert len(chart_data_locked["data_points"]) == 3
        # Third data point defect rate = 0.25
        assert chart_data_locked["data_points"][2]["x_value"] == 0.25
        
        # UCL for third batch = cl + 3 * sqrt(cl * (1-cl) / n)
        # cl = 0.0367, n = 100 => spread = 3 * sqrt(0.0367 * 0.9633 / 100) = 3 * 0.0188 = 0.0564
        # UCL = 0.0367 + 0.0564 = 0.0931. 0.25 is way above 0.0931, so it should trigger Rule 1 alarm!
        third_ucl = chart_data_locked["limits"]["ucl_list"][2]
        assert third_ucl < 0.15
        
        # Check alarm generation
        alarms_result = await db_session.execute(
            select(SPCAlarm).where(SPCAlarm.ic_id == ic.ic_id)
        )
        alarms = alarms_result.scalars().all()
        assert len(alarms) >= 1
        rule1_alarm = [a for a in alarms if a.rule_no == 1]
        assert len(rule1_alarm) == 1
        assert rule1_alarm[0].status == "open"

        # 6. Unlock, add more data to trigger Snapshot v2
        ic_unlocked = await lock_unlock_control_limits(db_session, user_id, ic.ic_id, False)
        assert ic_unlocked.control_limits_locked is False

        batch4 = await add_sample_batch(db_session, user_id, ic.ic_id, {
            "batch_no": "B004",
            "sampled_at": "2026-05-22T13:00:00",
            "inspected_count": 100,
            "defect_count": 1,
        })

        # Lock again => creates version 2
        ic_locked_2 = await lock_unlock_control_limits(db_session, user_id, ic.ic_id, True)
        assert ic_locked_2.control_limits_locked is True

        snapshots_v2 = await list_snapshots(db_session, ic.ic_id)
        assert len(snapshots_v2) == 2
        # Order is typically latest first
        snapshots_v2_sorted = sorted(snapshots_v2, key=lambda x: x.version_no)
        assert snapshots_v2_sorted[0].version_no == 1
        assert snapshots_v2_sorted[1].version_no == 2
        assert snapshots_v2_sorted[0].is_active is False
        assert snapshots_v2_sorted[1].is_active is True  # New snapshot is active by default

        # 7. Test historical snapshot switching
        # Switch back to Version 1
        v1_activated = await activate_snapshot(db_session, user_id, ic.ic_id, snapshots_v2_sorted[0].snapshot_id, change_reason="Test rollback")
        assert v1_activated.version_no == 1
        assert v1_activated.is_active is True

        # Fetch v2 snapshot to make sure it was deactivated
        snapshots_v3 = await list_snapshots(db_session, ic.ic_id)
        v2_snap = [s for s in snapshots_v3 if s.version_no == 2][0]
        assert v2_snap.is_active is False

    finally:
        # Cleanup created characteristics, batches, and snapshots to keep database clean
        for ic_id in created_ic_ids:
            await db_session.execute(delete(SPCAlarm).where(SPCAlarm.ic_id == ic_id))
            await db_session.execute(delete(ControlLimitSnapshot).where(ControlLimitSnapshot.ic_id == ic_id))
            await db_session.execute(delete(SampleBatch).where(SampleBatch.ic_id == ic_id))
            await db_session.execute(delete(InspectionCharacteristic).where(InspectionCharacteristic.ic_id == ic_id))
        await db_session.commit()
