import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import text

from app.models.capa import CAPAEightD
from app.models.capa_lesson import CapaLessonLearned
from app.models.factory import Factory
from app.models.fmea import FMEADocument
from app.models.iqc_inspection import IqcInspection
from app.models.mes import MESConnection, MESEquipmentStatus, MESScrapRecord
from app.models.product_line import ProductLine
from app.models.product_type import ProductType
from app.models.spc import InspectionCharacteristic, SPCAlarm
from app.models.supplier import Supplier, SupplierEvaluation, SupplierSCAR
from app.services.recommendation_sources_extra import (
    IQCSource,
    LessonsLearnedSource,
    MESSource,
    SameTypeProductKBSource,
    SPCAnomalySource,
    SupplierHistorySource,
)
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


# ── SameTypeProductKBSource (Task 9) ───────────────────────────────────────


async def _embedding_dim(db) -> int | None:
    """Query the actual pgvector dimension configured for document_embeddings."""
    result = await db.execute(text("""
        SELECT atttypmod FROM pg_attribute
        WHERE attrelid = 'document_embeddings'::regclass AND attname = 'embedding'
    """))
    row = result.fetchone()
    return row[0] if row else None


def _vec_str(dim: int, hot_idx: int) -> str:
    """Return a pgvector literal with a single hot dimension."""
    parts = ["0.0"] * dim
    parts[hot_idx] = "1.0"
    return "[" + ",".join(parts) + "]"


async def _seed_product_type(db, code: str):
    pt = ProductType(code=code, name=f"Type {code}")
    db.add(pt)
    await db.flush()
    await db.refresh(pt)
    return pt


async def _seed_pl(db, code: str, factory_id: uuid.UUID, product_type_code: str | None = None):
    pl = ProductLine(code=code, name=f"PL {code}", factory_id=factory_id, product_type_code=product_type_code)
    db.add(pl)
    await db.flush()
    await db.refresh(pl)
    return pl


async def _seed_fmea_doc(db, factory_id: uuid.UUID, pl_code: str, user_id: uuid.UUID, suffix: str):
    node_id = str(uuid.uuid4())
    doc = FMEADocument(
        fmea_id=uuid.uuid4(),
        document_no=f"PFMEA-{suffix}",
        title=f"FMEA {suffix}",
        fmea_type="PFMEA",
        product_line_code=pl_code,
        factory_id=factory_id,
        created_by=user_id,
        status="approved",
        graph_data={
            "nodes": [
                {"id": node_id, "type": "FailureCause", "name": f"cause {suffix}", "description": f"desc {suffix}"}
            ],
            "edges": [],
        },
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    return doc, node_id


async def _seed_embedding(
    db,
    dim: int,
    entity_type: str,
    entity_id: uuid.UUID,
    entity_field: str,
    chunk_text: str,
    factory_id: uuid.UUID,
    pl_code: str,
    model: str,
    hot_idx: int = 0,
    node_id: str | None = None,
    metadata: dict | None = None,
):
    emb_id = uuid.uuid4()
    await db.execute(
        text("""
            INSERT INTO document_embeddings
                (id, entity_type, entity_id, node_id, entity_field, chunk_index, chunk_text,
                 embedding, product_line_code, factory_id, metadata, embedding_model)
            VALUES
                (:id, :entity_type, :entity_id, :node_id, :entity_field, 0, :chunk_text,
                 CAST(:embedding AS vector), :product_line_code, :factory_id, CAST(:metadata AS jsonb), :embedding_model)
        """),
        {
            "id": emb_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "node_id": node_id,
            "entity_field": entity_field,
            "chunk_text": chunk_text,
            "embedding": _vec_str(dim, hot_idx),
            "product_line_code": pl_code,
            "factory_id": factory_id,
            "metadata": json.dumps(metadata or {}),
            "embedding_model": model,
        },
    )
    await db.flush()
    return emb_id


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_same_type_should_skip_no_product_type(db, default_factory):
    """当前 PL 无 product_type_code → should_skip 返回原因。"""
    suffix = uuid.uuid4().hex[:8]
    pl_code = f"PL-NULL-{suffix}"
    pl = ProductLine(code=pl_code, name=f"PL NULL {suffix}", factory_id=default_factory.id, product_type_code=None)
    db.add(pl)
    await db.flush()

    src = SameTypeProductKBSource(db, MagicMock())
    ctx = RecommendationContext(
        capa_data={"d2_description": "螺栓尺寸超差", "product_line_code": pl_code},
        user_product_lines=None,
        stage="d4",
        factory_id=default_factory.id,
    )
    reason = await src.should_skip(ctx)
    assert reason is not None
    assert "无同类型产品 KB" in reason


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_same_type_retrieves_cross_pl(db, default_factory, admin_user):
    """同工厂、同 product_type、不同 PL 的 FMEA embedding 应被召回。"""
    suffix = uuid.uuid4().hex[:8]
    pt_code = f"PT-CROSS-{suffix}"
    await _seed_product_type(db, pt_code)

    pl_current = await _seed_pl(db, f"PL-CUR-{suffix}", default_factory.id, pt_code)
    pl_other = await _seed_pl(db, f"PL-OTH-{suffix}", default_factory.id, pt_code)

    dim = await _embedding_dim(db)
    if dim is None:
        pytest.skip("document_embeddings.embedding column not present (pgvector schema not available)")

    doc, node_id = await _seed_fmea_doc(db, default_factory.id, pl_other.code, admin_user.user_id, f"CROSS-{suffix}")
    await _seed_embedding(
        db, dim, "fmea_node", doc.fmea_id, "name", "螺栓尺寸超差",
        default_factory.id, pl_other.code, "test-model", hot_idx=0, node_id=node_id,
        metadata={"node_type": "FailureCause"},
    )

    query_vec = [0.0] * dim
    query_vec[0] = 1.0

    emb = MagicMock()
    emb.embed = AsyncMock(return_value=[query_vec])
    src = SameTypeProductKBSource(db, emb)
    ctx = RecommendationContext(
        capa_data={"d2_description": "螺栓尺寸超差", "product_line_code": pl_current.code},
        user_product_lines=None,
        stage="d4",
        factory_id=default_factory.id,
        fmea_docs=[],
    )
    cands = await src.retrieve(ctx)

    assert len(cands) > 0
    assert all(c.source == "same_type_product_kb" for c in cands)
    assert all(c.metadata.get("product_type_code") == pt_code for c in cands)
    assert all(c.metadata.get("product_line_code") == pl_other.code for c in cands)
    assert all(c.metadata.get("factory_id") == str(default_factory.id) for c in cands)
    returned_doc_nos = {c.metadata.get("fmea_document_no") for c in cands}
    assert doc.document_no in returned_doc_nos


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_same_type_factory_isolation(db, default_factory, admin_user):
    """同 product_type 但跨工厂时，只返回当前工厂的候选。"""
    suffix = uuid.uuid4().hex[:8]
    pt_code = f"PT-ISO-{suffix}"
    await _seed_product_type(db, pt_code)

    pl_current = await _seed_pl(db, f"PL-CUR-{suffix}", default_factory.id, pt_code)
    pl_other_a = await _seed_pl(db, f"PL-OTH-A-{suffix}", default_factory.id, pt_code)

    factory_b = Factory(code=f"FB-{suffix}", name=f"Factory B {suffix}")
    db.add(factory_b)
    await db.flush()
    await db.refresh(factory_b)
    pl_other_b = await _seed_pl(db, f"PL-OTH-B-{suffix}", factory_b.id, pt_code)

    dim = await _embedding_dim(db)
    if dim is None:
        pytest.skip("document_embeddings.embedding column not present (pgvector schema not available)")

    fmea_a, node_id_a = await _seed_fmea_doc(db, default_factory.id, pl_other_a.code, admin_user.user_id, f"ISO-A-{suffix}")
    fmea_b, node_id_b = await _seed_fmea_doc(db, factory_b.id, pl_other_b.code, admin_user.user_id, f"ISO-B-{suffix}")

    await _seed_embedding(
        db, dim, "fmea_node", fmea_a.fmea_id, "name", "问题 A",
        default_factory.id, pl_other_a.code, "test-model", hot_idx=0, node_id=node_id_a,
        metadata={"node_type": "FailureCause"},
    )
    await _seed_embedding(
        db, dim, "fmea_node", fmea_b.fmea_id, "name", "问题 B",
        factory_b.id, pl_other_b.code, "test-model", hot_idx=1, node_id=node_id_b,
        metadata={"node_type": "FailureCause"},
    )

    query_vec = [0.0] * dim
    query_vec[0] = 1.0

    emb = MagicMock()
    emb.embed = AsyncMock(return_value=[query_vec])
    src = SameTypeProductKBSource(db, emb)
    ctx = RecommendationContext(
        capa_data={"d2_description": "问题 A", "product_line_code": pl_current.code},
        user_product_lines=None,
        stage="d4",
        factory_id=default_factory.id,
        fmea_docs=[],
    )
    cands = await src.retrieve(ctx)

    assert len(cands) > 0
    returned_doc_nos = {c.metadata.get("fmea_document_no") for c in cands}
    assert fmea_a.document_no in returned_doc_nos
    assert fmea_b.document_no not in returned_doc_nos


# ── LessonsLearnedSource (Task 10) ───────────────────────────────────────────


def _make_capa(db, factory_id, report_id, document_no):
    capa = CAPAEightD(
        report_id=report_id,
        document_no=document_no,
        title=f"CAPA {document_no}",
        factory_id=factory_id,
        product_line_code="DC-DC-100",
        status="D2_DESCRIPTION",
    )
    db.add(capa)
    return capa


def _make_lesson(db, factory_id, capa_id, lesson_id, lesson_text, category="prevention"):
    lesson = CapaLessonLearned(
        lesson_id=lesson_id,
        capa_id=capa_id,
        factory_id=factory_id,
        product_line_code="DC-DC-100",
        lesson_text=lesson_text,
        lesson_text_normalized=lesson_text,
        category=category,
        source_d_step="d5",
    )
    db.add(lesson)
    return lesson


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_lessons_should_skip_no_embedding(db, default_factory):
    src = LessonsLearnedSource(db, None)
    ctx = RecommendationContext(
        capa_data={"d2_description": "螺栓尺寸超差", "product_line_code": "DC-DC-100"},
        user_product_lines=["DC-DC-100"],
        stage="d4",
        factory_id=default_factory.id,
    )
    reason = await src.should_skip(ctx)
    assert reason == "未配置 embedding"


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_lessons_should_skip_no_lessons(db, default_factory):
    src = LessonsLearnedSource(db, MagicMock())
    ctx = RecommendationContext(
        capa_data={"d2_description": "螺栓尺寸超差", "product_line_code": "DC-DC-100"},
        user_product_lines=["DC-DC-100"],
        stage="d4",
        factory_id=default_factory.id,
    )
    reason = await src.should_skip(ctx)
    assert reason is not None
    assert "经验教训" in reason or "无" in reason


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_lessons_retrieves_when_data(db, default_factory):
    suffix = uuid.uuid4().hex[:8]
    doc_no = f"8D-LL-{suffix}"
    report_id = uuid.uuid4()
    lesson_id = uuid.uuid4()

    _make_capa(db, default_factory.id, report_id, doc_no)
    _make_lesson(
        db,
        default_factory.id,
        report_id,
        lesson_id,
        "预防螺栓尺寸超差",
        category="prevention",
    )
    await db.flush()

    dim = await _embedding_dim(db)
    if dim is None:
        pytest.skip("document_embeddings.embedding column not present (pgvector schema not available)")

    await _seed_embedding(
        db,
        dim,
        "capa_lesson",
        lesson_id,
        "lesson_text",
        "预防螺栓尺寸超差",
        default_factory.id,
        "DC-DC-100",
        "test-model",
        hot_idx=0,
    )

    query_vec = [0.0] * dim
    query_vec[0] = 1.0

    emb = MagicMock()
    emb.embed = AsyncMock(return_value=[query_vec])
    src = LessonsLearnedSource(db, emb)
    ctx = RecommendationContext(
        capa_data={"d2_description": "螺栓尺寸超差", "product_line_code": "DC-DC-100"},
        user_product_lines=["DC-DC-100"],
        stage="d4",
        factory_id=default_factory.id,
    )
    cands = await src.retrieve(ctx)

    assert len(cands) > 0
    assert all(c.source == "lessons_learned" for c in cands)
    assert all(c.metadata.get("source_capa_document_no") is not None for c in cands)
    assert any(c.metadata.get("source_capa_document_no") == doc_no for c in cands)
    assert any(c.metadata.get("category") == "prevention" for c in cands)
    assert any(c.metadata.get("lesson_id") == str(lesson_id) for c in cands)
    assert any("预防螺栓尺寸超差" in c.content for c in cands)


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_lessons_factory_isolation(db, default_factory, admin_user):
    suffix = uuid.uuid4().hex[:8]
    other = Factory(id=uuid.uuid4(), code=f"OTHER-LL-{suffix}", name="Other Lessons Factory")
    db.add(other)
    await db.flush()

    report_a = uuid.uuid4()
    lesson_a = uuid.uuid4()
    _make_capa(db, default_factory.id, report_a, "8D-A")
    _make_lesson(db, default_factory.id, report_a, lesson_a, "问题 A", category="prevention")

    report_b = uuid.uuid4()
    lesson_b = uuid.uuid4()
    _make_capa(db, other.id, report_b, "8D-B")
    _make_lesson(db, other.id, report_b, lesson_b, "问题 B", category="prevention")
    await db.flush()

    dim = await _embedding_dim(db)
    if dim is None:
        pytest.skip("document_embeddings.embedding column not present (pgvector schema not available)")

    await _seed_embedding(
        db,
        dim,
        "capa_lesson",
        lesson_a,
        "lesson_text",
        "问题 A",
        default_factory.id,
        "DC-DC-100",
        "test-model",
        hot_idx=0,
    )
    await _seed_embedding(
        db,
        dim,
        "capa_lesson",
        lesson_b,
        "lesson_text",
        "问题 B",
        other.id,
        "DC-DC-100",
        "test-model",
        hot_idx=1,
    )

    query_vec = [0.0] * dim
    query_vec[0] = 1.0

    emb = MagicMock()
    emb.embed = AsyncMock(return_value=[query_vec])
    src = LessonsLearnedSource(db, emb)
    ctx = RecommendationContext(
        capa_data={"d2_description": "问题 A", "product_line_code": "DC-DC-100"},
        user_product_lines=["DC-DC-100"],
        stage="d4",
        factory_id=default_factory.id,
    )
    cands = await src.retrieve(ctx)

    assert len(cands) > 0, "default 工厂有经验教训数据，retrieve 不应为空"
    returned_doc_nos = {c.metadata.get("source_capa_document_no") for c in cands}
    assert "8D-A" in returned_doc_nos
    assert "8D-B" not in returned_doc_nos
    assert all(c.metadata.get("factory_id") == str(default_factory.id) for c in cands)
