import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.capa import CAPAEightD
from app.models.factory import Factory
from app.models.fmea import FMEADocument
from app.models.iqc_inspection import IqcInspection
from app.models.mes import MESConnection, MESEquipmentStatus, MESScrapRecord
from app.models.spc import InspectionCharacteristic, SPCAlarm
from app.models.supplier import Supplier, SupplierEvaluation, SupplierSCAR
from app.services.recommendation_sources_extra import IQCSource, MESSource, SPCAnomalySource, SupplierHistorySource
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


def _make_supplier(db, factory_id, admin_user, supplier_no):
    supplier = Supplier(
        supplier_id=uuid.uuid4(),
        supplier_no=supplier_no,
        factory_id=factory_id,
        name=f"Supplier {supplier_no}",
        short_name=supplier_no,
        created_by=admin_user.user_id,
        status="approved",
    )
    db.add(supplier)
    return supplier


def _make_supplier_evaluation(db, supplier_id, factory_id, admin_user, grade="A"):
    evaluation = SupplierEvaluation(
        eval_id=uuid.uuid4(),
        supplier_id=supplier_id,
        factory_id=factory_id,
        eval_period="2026-Q2",
        eval_type="季度",
        quality_score=85.0,
        delivery_score=85.0,
        service_score=85.0,
        capa_count=0,
        finding_count=0,
        premium_freight_count=0,
        customer_disruption_count=0,
        capa_penalty=0.0,
        finding_penalty=0.0,
        premium_freight_penalty=0.0,
        customer_disruption_penalty=0.0,
        total_score=85.0,
        grade=grade,
        evaluated_by=admin_user.user_id,
    )
    db.add(evaluation)
    return evaluation


def _make_iqc_inspection(
    db,
    factory_id,
    supplier_id,
    admin_user,
    inspection_no,
    product_line_code="DC-DC-100",
    defect_qty=0,
    defect_description=None,
    inspection_date=None,
    part_no=None,
    lot_qty=10,
):
    if inspection_date is None:
        inspection_date = datetime.now(timezone.utc).date()
    # inspection_no is globally unique; suffix with UUID to avoid collisions
    unique_no = f"{inspection_no}-{uuid.uuid4().hex[:8]}"
    inspection = IqcInspection(
        inspection_id=uuid.uuid4(),
        inspection_no=unique_no,
        supplier_id=supplier_id,
        factory_id=factory_id,
        product_line_code=product_line_code,
        defect_qty=defect_qty,
        defect_description=defect_description,
        inspection_date=inspection_date,
        part_no=part_no,
        lot_qty=lot_qty,
        inspection_result="rejected" if defect_qty > 0 else "passed",
        inspected_by=admin_user.user_id,
        judged_by=admin_user.user_id,
    )
    db.add(inspection)
    return inspection


@pytest.mark.asyncio
async def test_iqc_should_skip_no_defects(db, default_factory):
    src = IQCSource(db)
    ctx = RecommendationContext(
        capa_data={"product_line_code": "DC-DC-100"},
        user_product_lines=["DC-DC-100"],
        stage="d4",
        factory_id=default_factory.id,
    )
    reason = await src.should_skip(ctx)
    assert reason is not None
    assert "IQC" in reason or "不良" in reason


@pytest.mark.asyncio
async def test_iqc_retrieves_when_defects(db, default_factory, admin_user):
    supplier = _make_supplier(db, default_factory.id, admin_user, "SUP-IQC-01")
    await db.flush()
    _make_iqc_inspection(
        db,
        default_factory.id,
        supplier.supplier_id,
        admin_user,
        "IQC-2026-001",
        defect_qty=3,
        defect_description="尺寸超差",
        part_no="PART-001",
    )
    await db.flush()

    src = IQCSource(db)
    ctx = RecommendationContext(
        capa_data={"product_line_code": "DC-DC-100"},
        user_product_lines=["DC-DC-100"],
        stage="d4",
        factory_id=default_factory.id,
    )
    cands = await src.retrieve(ctx)
    assert len(cands) > 0
    assert all(c.source == "iqc" for c in cands)
    assert all(c.metadata.get("factory_id") == str(default_factory.id) for c in cands)
    assert any(c.metadata.get("part_no") == "PART-001" for c in cands)
    assert any("尺寸超差" in c.content for c in cands)


@pytest.mark.asyncio
async def test_iqc_factory_isolation(db, default_factory, admin_user):
    other = Factory(id=uuid.uuid4(), code="OTHER", name="Other")
    db.add(other)
    await db.flush()

    supplier_a = _make_supplier(db, default_factory.id, admin_user, "SUP-IQC-A")
    await db.flush()
    inspection_a = _make_iqc_inspection(
        db,
        default_factory.id,
        supplier_a.supplier_id,
        admin_user,
        "IQC-2026-A",
        defect_qty=5,
        defect_description="外观划伤",
        part_no="PART-A",
    )

    supplier_b = _make_supplier(db, other.id, admin_user, "SUP-IQC-B")
    await db.flush()
    inspection_b = _make_iqc_inspection(
        db,
        other.id,
        supplier_b.supplier_id,
        admin_user,
        "IQC-2026-B",
        product_line_code="DC-DC-100",
        defect_qty=7,
        defect_description="镀层脱落",
        part_no="PART-B",
    )
    await db.flush()

    src = IQCSource(db)
    ctx = RecommendationContext(
        capa_data={"product_line_code": "DC-DC-100"},
        user_product_lines=["DC-DC-100"],
        stage="d4",
        factory_id=default_factory.id,
    )
    cands = await src.retrieve(ctx)

    assert len(cands) > 0, "default 工厂有 IQC 不良数据，retrieve 不应为空"
    assert all(c.metadata.get("factory_id") == str(default_factory.id) for c in cands)

    other_inspection_ids = {str(inspection_b.inspection_id)}
    assert not any(c.metadata.get("inspection_id") in other_inspection_ids for c in cands)
    assert any(c.metadata.get("inspection_id") == str(inspection_a.inspection_id) for c in cands)


@pytest.mark.asyncio
async def test_supplier_should_skip_no_suppliers(db, default_factory):
    src = SupplierHistorySource(db)
    ctx = RecommendationContext(
        capa_data={"product_line_code": "DC-DC-100"},
        user_product_lines=["DC-DC-100"],
        stage="d4",
        factory_id=default_factory.id,
    )
    reason = await src.should_skip(ctx)
    assert reason is not None
    assert "无关联供应商历史" in reason


@pytest.mark.asyncio
async def test_supplier_retrieves_when_history(db, default_factory, admin_user):
    supplier = _make_supplier(db, default_factory.id, admin_user, "SUP-HIST-01")
    await db.flush()
    _make_supplier_evaluation(db, supplier.supplier_id, default_factory.id, admin_user, grade="A")
    _make_iqc_inspection(
        db,
        default_factory.id,
        supplier.supplier_id,
        admin_user,
        "IQC-SUP-001",
        defect_qty=3,
        defect_description="镀层脱落",
        part_no="PART-SUP-001",
        lot_qty=100,
    )
    await db.flush()

    src = SupplierHistorySource(db)
    ctx = RecommendationContext(
        capa_data={"product_line_code": "DC-DC-100"},
        user_product_lines=["DC-DC-100"],
        stage="d4",
        factory_id=default_factory.id,
    )
    cands = await src.retrieve(ctx)
    assert len(cands) > 0
    assert all(c.source == "supplier_history" for c in cands)
    assert all(c.metadata.get("factory_id") == str(default_factory.id) for c in cands)
    assert any(c.metadata.get("supplier_id") == str(supplier.supplier_id) for c in cands)
    assert all(c.metadata.get("grade") is not None for c in cands)
    assert any("评级" in c.content and "PPM=" in c.content for c in cands)


@pytest.mark.asyncio
async def test_supplier_factory_isolation(db, default_factory, admin_user):
    other = Factory(id=uuid.uuid4(), code="OTHER", name="Other")
    db.add(other)
    await db.flush()

    supplier_a = _make_supplier(db, default_factory.id, admin_user, "SUP-HIST-A")
    await db.flush()
    _make_iqc_inspection(
        db,
        default_factory.id,
        supplier_a.supplier_id,
        admin_user,
        "IQC-SUP-A",
        defect_qty=5,
        defect_description="外观划伤",
        part_no="PART-A",
        lot_qty=100,
    )

    supplier_b = _make_supplier(db, other.id, admin_user, "SUP-HIST-B")
    await db.flush()
    _make_iqc_inspection(
        db,
        other.id,
        supplier_b.supplier_id,
        admin_user,
        "IQC-SUP-B",
        product_line_code="DC-DC-100",
        defect_qty=7,
        defect_description="镀层脱落",
        part_no="PART-B",
        lot_qty=100,
    )
    await db.flush()

    src = SupplierHistorySource(db)
    ctx = RecommendationContext(
        capa_data={"product_line_code": "DC-DC-100"},
        user_product_lines=["DC-DC-100"],
        stage="d4",
        factory_id=default_factory.id,
    )
    cands = await src.retrieve(ctx)

    assert len(cands) > 0, "default 工厂有 IQC 不良数据，retrieve 不应为空"
    assert all(c.metadata.get("factory_id") == str(default_factory.id) for c in cands)

    other_supplier_ids = {str(supplier_b.supplier_id)}
    assert not any(c.metadata.get("supplier_id") in other_supplier_ids for c in cands)
    assert any(c.metadata.get("supplier_id") == str(supplier_a.supplier_id) for c in cands)


def _make_scar(db, supplier_id, factory_id, admin_user, capa_ref_id, scar_no):
    scar = SupplierSCAR(
        scar_id=uuid.uuid4(),
        scar_no=scar_no,
        supplier_id=supplier_id,
        factory_id=factory_id,
        source_type="capa",
        source_id=capa_ref_id,
        capa_ref_id=capa_ref_id,
        description="SCAR linked to CAPA",
        status="open",
        issued_by=admin_user.user_id,
    )
    db.add(scar)
    return scar


@pytest.mark.asyncio
async def test_supplier_retrieves_via_scar(db, default_factory, admin_user):
    # Build CAPA with report_id=R in default factory
    report_id = uuid.uuid4()
    capa = CAPAEightD(
        report_id=report_id,
        document_no="8D-SCAR-REC-001",
        title="SCAR recommendation test",
        factory_id=default_factory.id,
        product_line_code="DC-DC-100",
        status="D2_DESCRIPTION",
    )
    db.add(capa)

    supplier = _make_supplier(db, default_factory.id, admin_user, "SUP-SCAR-01")
    await db.flush()

    # Link supplier to CAPA via SupplierSCAR, but DO NOT seed IQC defects
    _make_scar(
        db,
        supplier.supplier_id,
        default_factory.id,
        admin_user,
        capa_ref_id=report_id,
        scar_no="SCAR-REC-001",
    )
    await db.flush()

    src = SupplierHistorySource(db)
    ctx = RecommendationContext(
        capa_data={"product_line_code": "DC-DC-100", "report_id": report_id},
        user_product_lines=["DC-DC-100"],
        stage="d4",
        factory_id=default_factory.id,
    )

    # should_skip returns None because the SCAR path activates now that report_id is in capa_data
    skip_reason = await src.should_skip(ctx)
    assert skip_reason is None

    # retrieve must also find supplier_A through the SCAR path
    cands = await src.retrieve(ctx)
    assert len(cands) > 0
    assert all(c.source == "supplier_history" for c in cands)
    assert any(c.metadata.get("supplier_id") == str(supplier.supplier_id) for c in cands)


def _make_mes_connection(db, factory_id, admin_user, name="MES-CONN-01"):
    conn = MESConnection(
        connection_id=uuid.uuid4(),
        name=name,
        connector_type="mock",
        config={},
        is_active=True,
        product_line_code="DC-DC-100",
        factory_id=factory_id,
        created_by=admin_user.user_id,
    )
    db.add(conn)
    return conn


def _make_scrap_record(
    db,
    factory_id,
    connection_id,
    external_id,
    defect_type="划伤",
    defect_qty=5,
    total_qty=100,
    defect_description=None,
):
    record = MESScrapRecord(
        scrap_id=uuid.uuid4(),
        connection_id=connection_id,
        factory_id=factory_id,
        external_id=external_id,
        defect_type=defect_type,
        defect_qty=defect_qty,
        total_qty=total_qty,
        defect_description=defect_description,
        recorded_at=datetime.now(timezone.utc),
        product_line_code="DC-DC-100",
    )
    db.add(record)
    return record


def _make_equipment_status(
    db,
    factory_id,
    connection_id,
    external_id,
    equipment_code="EQ-01",
    equipment_name=None,
    downtime_reason=None,
):
    status = MESEquipmentStatus(
        record_id=uuid.uuid4(),
        connection_id=connection_id,
        factory_id=factory_id,
        external_id=external_id,
        equipment_code=equipment_code,
        equipment_name=equipment_name,
        status="downtime",
        recorded_at=datetime.now(timezone.utc),
        downtime_reason=downtime_reason,
        product_line_code="DC-DC-100",
    )
    db.add(status)
    return status


@pytest.mark.asyncio
async def test_mes_should_skip_no_data(db, default_factory):
    src = MESSource(db)
    ctx = RecommendationContext(
        capa_data={"product_line_code": "DC-DC-100"},
        user_product_lines=["DC-DC-100"],
        stage="d4",
        factory_id=default_factory.id,
    )
    reason = await src.should_skip(ctx)
    assert reason is not None
    assert "MES" in reason or "暂无" in reason


@pytest.mark.asyncio
async def test_mes_retrieves_when_data(db, default_factory, admin_user):
    conn = _make_mes_connection(db, default_factory.id, admin_user)
    await db.flush()
    _make_scrap_record(
        db,
        default_factory.id,
        conn.connection_id,
        "SCRAP-001",
        defect_type="划伤",
        defect_qty=3,
        defect_description="表面划伤",
    )
    _make_equipment_status(
        db,
        default_factory.id,
        conn.connection_id,
        "EQ-001",
        equipment_code="P1-01",
        equipment_name="贴片机 1",
        downtime_reason="轨道卡滞",
    )
    await db.flush()

    src = MESSource(db)
    ctx = RecommendationContext(
        capa_data={"product_line_code": "DC-DC-100"},
        user_product_lines=["DC-DC-100"],
        stage="d4",
        factory_id=default_factory.id,
    )
    reason = await src.should_skip(ctx)
    assert reason is None
    cands = await src.retrieve(ctx)
    assert len(cands) > 0
    assert all(c.source == "mes" for c in cands)
    assert all(c.metadata.get("factory_id") == str(default_factory.id) for c in cands)
    assert any(c.metadata.get("scrap_record_id") for c in cands)
    assert any(c.metadata.get("equipment_id") for c in cands)
    assert any("MES 报废" in c.content for c in cands)
    assert any("设备停机" in c.content for c in cands)


@pytest.mark.asyncio
async def test_mes_factory_isolation(db, default_factory, admin_user):
    other = Factory(id=uuid.uuid4(), code="OTHER", name="Other")
    db.add(other)
    await db.flush()

    conn_a = _make_mes_connection(db, default_factory.id, admin_user, "MES-CONN-A")
    conn_b = _make_mes_connection(db, other.id, admin_user, "MES-CONN-B")
    await db.flush()

    scrap_a = _make_scrap_record(
        db,
        default_factory.id,
        conn_a.connection_id,
        "SCRAP-A",
        defect_type="裂纹",
        defect_qty=2,
    )
    equip_a = _make_equipment_status(
        db,
        default_factory.id,
        conn_a.connection_id,
        "EQ-A",
        equipment_code="P1-A",
        downtime_reason="缺料停机",
    )

    scrap_b = _make_scrap_record(
        db,
        other.id,
        conn_b.connection_id,
        "SCRAP-B",
        defect_type="变形",
        defect_qty=4,
    )
    equip_b = _make_equipment_status(
        db,
        other.id,
        conn_b.connection_id,
        "EQ-B",
        equipment_code="P1-B",
        downtime_reason="气压不足",
    )
    await db.flush()

    src = MESSource(db)
    ctx = RecommendationContext(
        capa_data={"product_line_code": "DC-DC-100"},
        user_product_lines=["DC-DC-100"],
        stage="d4",
        factory_id=default_factory.id,
    )
    cands = await src.retrieve(ctx)

    assert len(cands) > 0, "default 工厂有 MES 数据，retrieve 不应为空"
    assert all(c.metadata.get("factory_id") == str(default_factory.id) for c in cands)

    other_ids = {str(scrap_b.scrap_id), str(equip_b.record_id)}
    assert not any(
        c.metadata.get("scrap_record_id") in other_ids
        or c.metadata.get("equipment_id") in other_ids
        for c in cands
    )
    assert any(c.metadata.get("scrap_record_id") == str(scrap_a.scrap_id) for c in cands)
    assert any(c.metadata.get("equipment_id") == str(equip_a.record_id) for c in cands)
