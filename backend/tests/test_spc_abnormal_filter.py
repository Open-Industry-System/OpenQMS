"""Tests for list_inspection_characteristics abnormal filter (仪表盘「SPC 异常」下钻)."""
import os
import uuid
from datetime import UTC, datetime, timedelta

os.environ.setdefault("SECRET_KEY", "test-non-default-secret-key")

import pytest

from app.models.spc import InspectionCharacteristic, SPCAlarm
from app.services.spc_service import list_inspection_characteristics

import app.models  # noqa: F401 — register all FK-referenced tables


def _pl_code() -> str:
    return "T" + uuid.uuid4().hex[:12]


def _make_ic(ic_code, pl, factory_id, created_by_id, process_name):
    return InspectionCharacteristic(
        ic_code=ic_code,
        product_line=pl,
        factory_id=factory_id,
        process_name=process_name,
        characteristic_name="char",
        spec_upper=10.0,
        spec_lower=0.0,
        chart_type="xbar_r",
        subgroup_size=5,
        created_by_id=created_by_id,
    )


@pytest.mark.asyncio
async def test_abnormal_filter_returns_only_ics_with_open_recent_alarms(db, default_factory, admin_user):
    """abnormal=true 只返回近 7 天有 open 告警的检验特性。"""
    pl = _pl_code()
    ic_with = _make_ic(f"IC-{uuid.uuid4().hex[:8]}", pl, default_factory.id, admin_user.user_id, "P1")
    ic_without = _make_ic(f"IC-{uuid.uuid4().hex[:8]}", pl, default_factory.id, admin_user.user_id, "P2")
    db.add_all([ic_with, ic_without])
    await db.flush()

    db.add(SPCAlarm(
        ic_id=ic_with.ic_id,
        factory_id=default_factory.id,
        rule_no=1,
        severity="high",
        status="open",
        triggered_at=datetime.now(UTC),
    ))
    await db.flush()

    items, total = await list_inspection_characteristics(
        db, 1, 20, product_line=pl, factory_id=default_factory.id, abnormal=True
    )
    assert total == 1
    assert items[0].ic_id == ic_with.ic_id


@pytest.mark.asyncio
async def test_abnormal_filter_excludes_closed_and_old_alarms(db, default_factory, admin_user):
    """closed 告警与超过 7 天的告警不计入异常。"""
    pl = _pl_code()
    ic_closed = _make_ic(f"IC-{uuid.uuid4().hex[:8]}", pl, default_factory.id, admin_user.user_id, "PC")
    ic_old = _make_ic(f"IC-{uuid.uuid4().hex[:8]}", pl, default_factory.id, admin_user.user_id, "PO")
    db.add_all([ic_closed, ic_old])
    await db.flush()

    db.add(SPCAlarm(
        ic_id=ic_closed.ic_id, factory_id=default_factory.id, rule_no=1,
        severity="high", status="closed", triggered_at=datetime.now(UTC),
    ))
    db.add(SPCAlarm(
        ic_id=ic_old.ic_id, factory_id=default_factory.id, rule_no=1,
        severity="high", status="open", triggered_at=datetime.now(UTC) - timedelta(days=8),
    ))
    await db.flush()

    items, total = await list_inspection_characteristics(
        db, 1, 20, product_line=pl, factory_id=default_factory.id, abnormal=True
    )
    assert total == 0
    assert items == []
