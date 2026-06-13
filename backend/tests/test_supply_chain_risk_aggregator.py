import pytest
from datetime import date, timedelta
from uuid import uuid4
from sqlalchemy import select, func, text
from app.services.supply_chain_risk_map.aggregator import (
    aggregate_supply_chain_metrics,
    normalize_to_risk_index,
    ppm_to_risk_index,
)


@pytest.fixture
async def test_user(db, default_factory):
    """Create a minimal user row so FKs like created_by/evaluated_by resolve."""
    from app.models.user import User
    from app.models.role import RoleDefinition
    result = await db.execute(
        select(RoleDefinition).where(RoleDefinition.role_key == "admin")
    )
    role = result.scalar_one_or_none()
    if role is None:
        db.add(RoleDefinition(role_key="admin", name_zh="管理员", name_en="Admin", is_system=True, is_active=True))
        await db.flush()
        result = await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == "admin"))
        role = result.scalar_one()
    user = User(
        user_id=uuid4(), username=f"risk_agg_test_{uuid4().hex[:8]}",
        display_name="AggTest", password_hash="hashed",
        role_id=role.id, legacy_role="admin", is_active=True,
        factory_id=default_factory.id,
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_erp_on_time_rate_with_filter(db, test_user):
    """ERP on-time rate uses FILTER (WHERE actual_delivery_date <= delivery_date)."""
    from app.models.supplier import Supplier
    from app.models.erp import ERPPurchaseOrder, ERPConnection, ERPSupplier

    fid = test_user.factory_id
    conn_id = uuid4()
    supplier = Supplier(supplier_id=uuid4(), supplier_no="T-ONT-01", name="OntimeTest",
                         short_name="OT", status="approved", created_by=test_user.user_id,
                         factory_id=fid)
    db.add(supplier)
    erp_conn = ERPConnection(connection_id=conn_id, name="test_conn", connector_type="mock",
                               is_active=True, created_by=test_user.user_id, factory_id=fid)
    db.add(erp_conn)
    await db.flush()
    db.add(ERPSupplier(
        connection_id=conn_id, supplier_code="T-ONT-01",
        external_id="ERP-SUP-ONT-01", name=supplier.name,
        openqms_supplier_id=supplier.supplier_id, factory_id=fid,
    ))
    for i, (ad, dd) in enumerate([
        (date(2026, 6, 1), date(2026, 6, 5)),
        (date(2026, 6, 3), date(2026, 6, 5)),
        (date(2026, 6, 10), date(2026, 6, 5)),
    ]):
        db.add(ERPPurchaseOrder(
            po_id=uuid4(), connection_id=conn_id, external_id=f"PO-{i}",
            po_number=f"PO-2026-{i:03d}", line_number="1",
            supplier_code="T-ONT-01", delivery_date=dd,
            actual_delivery_date=ad, quantity=100, unit_price=10,
            status="completed", product_line_code=None, factory_id=fid,
        ))
    await db.commit()

    result = await aggregate_supply_chain_metrics(db, [supplier.supplier_id], None, "2026-06")
    metrics = result[supplier.supplier_id]
    assert metrics["erp_on_time_rate"] == pytest.approx(66.67, rel=0.01)
    assert metrics["erp_on_time_rate_source"] == "erp_po"


@pytest.mark.asyncio
async def test_erp_fallback_to_evaluation(db, test_user):
    """When no PO data, fall back to supplier_evaluations.delivery_score."""
    from app.models.supplier import Supplier
    from app.models.supplier import SupplierEvaluation

    supplier = Supplier(supplier_id=uuid4(), supplier_no="T-FB-01", name="FallbackTest",
                         short_name="FB", status="approved", created_by=test_user.user_id,
                         factory_id=test_user.factory_id)
    db.add(supplier)
    db.add(SupplierEvaluation(
        eval_id=uuid4(), supplier_id=supplier.supplier_id,
        eval_period="2026-06", eval_type="monthly",
        quality_score=80, delivery_score=75, service_score=70,
        capa_count=0, finding_count=0, premium_freight_count=0,
        customer_disruption_count=0, capa_penalty=0, finding_penalty=0,
        premium_freight_penalty=0, customer_disruption_penalty=0,
        total_score=75, grade="B", notes="fallback test",
        evaluated_by=test_user.user_id, factory_id=test_user.factory_id,
    ))
    await db.commit()

    result = await aggregate_supply_chain_metrics(db, [supplier.supplier_id], None, "2026-06")
    metrics = result[supplier.supplier_id]
    assert metrics["erp_on_time_rate"] == 75.0
    assert metrics["erp_on_time_rate_source"] == "supplier_evaluation_fallback"


@pytest.mark.asyncio
async def test_purchase_amount_pct_window_function(db, test_user):
    """Purchase amount % uses SUM(SUM(...)) OVER () window function."""
    from app.models.supplier import Supplier
    from app.models.erp import ERPPurchaseOrder, ERPConnection, ERPSupplier

    fid = test_user.factory_id
    conn_id = uuid4()
    s1 = Supplier(supplier_id=uuid4(), supplier_no="T-PCT-01", name="PctTest1",
                    short_name="P1", status="approved", created_by=test_user.user_id,
                    factory_id=fid)
    s2 = Supplier(supplier_id=uuid4(), supplier_no="T-PCT-02", name="PctTest2",
                    short_name="P2", status="approved", created_by=test_user.user_id,
                    factory_id=fid)
    db.add_all([s1, s2])
    erp_conn = ERPConnection(connection_id=conn_id, name="test_conn", connector_type="mock",
                               is_active=True, created_by=test_user.user_id, factory_id=fid)
    db.add(erp_conn)
    await db.flush()
    db.add(ERPSupplier(connection_id=conn_id, supplier_code="T-PCT-01", external_id="ERP-SUP-PCT-01", name=s1.name, openqms_supplier_id=s1.supplier_id, factory_id=fid))
    db.add(ERPSupplier(connection_id=conn_id, supplier_code="T-PCT-02", external_id="ERP-SUP-PCT-02", name=s2.name, openqms_supplier_id=s2.supplier_id, factory_id=fid))
    for sup, qty, price in [(s1, 300, 20), (s1, 100, 20), (s2, 200, 10)]:
        db.add(ERPPurchaseOrder(
            po_id=uuid4(), connection_id=conn_id, external_id=f"PO-{uuid4().hex[:6]}",
            po_number=f"PO-2026-{uuid4().hex[:4]}", line_number="1",
            supplier_code=sup.supplier_no, delivery_date=date(2026, 6, 15),
            quantity=qty, unit_price=price,
            status="completed", product_line_code=None, factory_id=fid,
        ))
    await db.commit()

    result = await aggregate_supply_chain_metrics(db, [s1.supplier_id, s2.supplier_id], None, "2026-06")
    assert result[s1.supplier_id]["purchase_amount_pct"] == pytest.approx(80.0, rel=0.01)
    assert result[s2.supplier_id]["purchase_amount_pct"] == pytest.approx(20.0, rel=0.01)


@pytest.mark.asyncio
async def test_ppm_calculation_with_period_filter(db, test_user):
    """PPM aggregates only inspections in the snapshot period."""
    from app.models.supplier import Supplier
    from app.models.iqc_inspection import IqcInspection

    supplier = Supplier(supplier_id=uuid4(), supplier_no="T-PPM-01", name="PPMTest",
                         short_name="PT", status="approved", created_by=test_user.user_id,
                         factory_id=test_user.factory_id)
    db.add(supplier)
    await db.flush()
    for i, (month, lot_qty, defect_qty) in enumerate([
        (6, 500, 10),
        (6, 500, 5),
        (6, 1000, 0),
        (5, 500, 20),
    ]):
        db.add(IqcInspection(
            inspection_id=uuid4(), inspection_no=f"IQC-PPM-{i:03d}",
            supplier_id=supplier.supplier_id,
            inspection_date=date(2026, month, 15),
            inspection_result="accepted" if defect_qty == 0 else "rejected",
            status="judged", lot_qty=lot_qty, defect_qty=defect_qty,
            product_line_code=None, factory_id=test_user.factory_id,
        ))
    await db.commit()

    result = await aggregate_supply_chain_metrics(db, [supplier.supplier_id], None, "2026-06")
    metrics = result[supplier.supplier_id]
    assert metrics["ppm_value"] == pytest.approx(7500.0, rel=0.01)
    assert metrics["ppm_source"] == "iqc_inspection"


@pytest.mark.asyncio
async def test_open_scar_count_time_point_logic(db, test_user):
    """SCAR count uses time-point: issued_date <= period_end AND (closed_date IS NULL OR closed_date > period_end)."""
    from app.models.supplier import Supplier, SupplierSCAR

    supplier = Supplier(supplier_id=uuid4(), supplier_no="T-SCAR-01", name="SCARTest",
                         short_name="ST", status="approved", created_by=test_user.user_id,
                         factory_id=test_user.factory_id)
    db.add(supplier)
    await db.flush()
    # SCAR issued before period end, still open — counted
    db.add(SupplierSCAR(
        scar_id=uuid4(), scar_no="SCAR-2026-001", supplier_id=supplier.supplier_id,
        source_type="internal", description="open scar",
        status="open", issued_date=date(2026, 6, 10),
    ))
    # SCAR issued before period end, closed after period end — counted (was open at period end)
    db.add(SupplierSCAR(
        scar_id=uuid4(), scar_no="SCAR-2026-002", supplier_id=supplier.supplier_id,
        source_type="internal", description="closed after period",
        status="closed", issued_date=date(2026, 6, 5), closed_date=date(2026, 7, 15),
    ))
    # SCAR issued after period end — NOT counted
    db.add(SupplierSCAR(
        scar_id=uuid4(), scar_no="SCAR-2026-003", supplier_id=supplier.supplier_id,
        source_type="internal", description="future scar",
        status="open", issued_date=date(2026, 7, 10),
    ))
    await db.commit()

    result = await aggregate_supply_chain_metrics(db, [supplier.supplier_id], None, "2026-06")
    metrics = result[supplier.supplier_id]
    assert metrics["open_scar_count"] == 2


# --- Pure function tests (no DB needed) ---

def test_normalize_higher_is_risk():
    result = normalize_to_risk_index({"score": {"raw_value": 65, "polarity": "higher_is_risk", "source": "risk_evaluation"}})
    assert result["score"]["risk_index"] == 65

def test_normalize_lower_is_risk():
    result = normalize_to_risk_index({"rate": {"raw_value": 92, "polarity": "lower_is_risk", "source": "erp_po"}})
    assert result["rate"]["risk_index"] == 8  # 100 - 92

def test_normalize_neutral_exposure():
    result = normalize_to_risk_index({"pct": {"raw_value": 35, "polarity": "neutral_exposure", "source": "erp_po"}})
    assert result["pct"]["risk_index"] == 35

def test_normalize_missing():
    result = normalize_to_risk_index({"rate": {"raw_value": None, "polarity": "lower_is_risk", "source": "missing"}})
    assert result["rate"]["risk_index"] is None
    assert result["rate"]["source"] == "missing"

def test_ppm_to_risk_index():
    assert ppm_to_risk_index(0) == 0
    assert ppm_to_risk_index(500) == 10
    assert ppm_to_risk_index(5000) == 100
    assert ppm_to_risk_index(10000) == 100