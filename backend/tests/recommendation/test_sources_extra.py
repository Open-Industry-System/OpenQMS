import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.factory import Factory
from app.models.fmea import FMEADocument
from app.models.spc import InspectionCharacteristic, SPCAlarm
from app.services.recommendation_sources_extra import SPCAnomalySource
from app.services.recommendation_types import RecommendationContext

pytestmark = pytest.mark.requires_db


def _make_ic(db, factory_id, admin_user, ic_code, process_name, characteristic_name):
    ic = InspectionCharacteristic(
        ic_id=uuid.uuid4(),
        ic_code=ic_code,
        product_line="DC-DC-100",
        factory_id=factory_id,
        process_name=process_name,
        characteristic_name=characteristic_name,
        spec_upper=10.0,
        spec_lower=0.0,
        chart_type="Xbar-R",
        subgroup_size=5,
        created_by_id=admin_user.user_id,
    )
    db.add(ic)
    return ic


def _make_alarm(db, ic, factory_id, rule_no=1):
    alarm = SPCAlarm(
        alarm_id=uuid.uuid4(),
        ic_id=ic.ic_id,
        factory_id=factory_id,
        rule_no=rule_no,
        severity="严重",
        status="open",
        triggered_at=datetime.now(timezone.utc),
    )
    db.add(alarm)
    return alarm


@pytest.mark.asyncio
async def test_spc_should_skip_no_alarms(db, default_factory):
    src = SPCAnomalySource(db)
    ctx = RecommendationContext(
        capa_data={"product_line_code": "DC-DC-100"},
        user_product_lines=["DC-DC-100"],
        stage="d4",
        factory_id=default_factory.id,
    )
    assert (await src.should_skip(ctx)) is not None


@pytest.mark.asyncio
async def test_spc_retrieves_when_alarms(db, default_factory, admin_user):
    ic = _make_ic(db, default_factory.id, admin_user, "IC-SPC-01", "车削工序", "尺寸")
    alarm = _make_alarm(db, ic, default_factory.id, rule_no=1)

    # Seed a matching PFMEA so spc_service.match_fmea_for_alarm returns a hit
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(),
        document_no="PFMEA-SPC-01",
        title="SPC匹配PFMEA",
        fmea_type="PFMEA",
        product_line_code="DC-DC-100",
        factory_id=default_factory.id,
        status="approved",
        created_by=admin_user.user_id,
        graph_data={
            "nodes": [
                {"id": "ps1", "type": "ProcessStep", "name": "车削工序"},
                {"id": "fm1", "type": "FailureMode", "name": "尺寸超差"},
            ],
            "edges": [
                {"source": "ps1", "target": "fm1", "type": "HAS_FAILURE_MODE"},
            ],
        },
    )
    db.add(fmea)
    await db.flush()

    src = SPCAnomalySource(db)
    ctx = RecommendationContext(
        capa_data={"product_line_code": "DC-DC-100"},
        user_product_lines=["DC-DC-100"],
        stage="d4",
        factory_id=default_factory.id,
    )
    cands = await src.retrieve(ctx)
    assert len(cands) > 0
    assert all(c.source == "spc_anomaly" for c in cands)


@pytest.mark.asyncio
async def test_spc_factory_isolation(db, default_factory, admin_user):
    other = Factory(id=uuid.uuid4(), code="OTHER", name="Other")
    db.add(other)
    await db.flush()

    # Default factory SPC data
    ic_a = _make_ic(db, default_factory.id, admin_user, "IC-SPC-A", "车削工序", "尺寸")
    alarm_a = _make_alarm(db, ic_a, default_factory.id, rule_no=1)

    # Other factory SPC data on the same product line
    ic_b = _make_ic(db, other.id, admin_user, "IC-SPC-B", "车削工序", "尺寸")
    alarm_b = _make_alarm(db, ic_b, other.id, rule_no=2)

    # Matching PFMEA in default factory
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(),
        document_no="PFMEA-SPC-02",
        title="SPC匹配PFMEA",
        fmea_type="PFMEA",
        product_line_code="DC-DC-100",
        factory_id=default_factory.id,
        status="approved",
        created_by=admin_user.user_id,
        graph_data={
            "nodes": [
                {"id": "ps1", "type": "ProcessStep", "name": "车削工序"},
                {"id": "fm1", "type": "FailureMode", "name": "尺寸超差"},
            ],
            "edges": [
                {"source": "ps1", "target": "fm1", "type": "HAS_FAILURE_MODE"},
            ],
        },
    )
    db.add(fmea)
    await db.flush()

    src = SPCAnomalySource(db)
    ctx = RecommendationContext(
        capa_data={"product_line_code": "DC-DC-100"},
        user_product_lines=["DC-DC-100"],
        stage="d4",
        factory_id=default_factory.id,
    )
    cands = await src.retrieve(ctx)

    # R13-修复：断言 default 数据命中（非空）+ other 数据不命中（factory_id 全是 default）
    assert len(cands) > 0, "default 工厂有 SPC 数据，retrieve 不应为空"
    assert all(c.metadata.get("factory_id") == str(default_factory.id) for c in cands)

    other_alarm_ids = {str(alarm_b.alarm_id)}
    assert not any(c.metadata.get("alarm_id") in other_alarm_ids for c in cands)
