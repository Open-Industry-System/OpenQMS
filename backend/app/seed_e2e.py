"""Deterministic idempotent E2E seed. Run: python -m app.seed_e2e

Idempotent: safe to re-run. Uses -E2E- infix doc numbers so cleanup never touches seed."""
import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select, update

from app.config import settings
from app.core.security import hash_password
from app.database import async_session
from app.models.factory import Factory, UserFactory
from app.models.product_line import ProductLine
from app.models.product_type import ProductType  # noqa: F401 — registers product_types in metadata
from app.models.role import RoleDefinition
from app.models.user import User
from app.schemas.capa_d3 import D3AdviceRequest, D3ImportRequest
from app.seed_e2e_constants import (
    D3_E2E_CUSTOMER_CODE, D3_E2E_CUSTOMER_SEGMENT, D3_E2E_ERP_CONNECTION_NAME,
    D3_E2E_LOT_NO, D3_E2E_MATERIAL_CODE, D3_E2E_PRODUCT_LINE, D3_E2E_SUPPLIER_NO,
    E2E_ACCOUNTS, E2E_FACTORY_DC100, E2E_FACTORY_SH, E2E_PRODUCT_LINE, E2E_PRODUCT_LINE_DEFAULT,
)

# Fixed UUIDs for idempotency
FACT_DC100_ID = uuid.UUID("00000000-0000-0000-0000-000000e20001")
FACT_SH_ID = uuid.UUID("00000000-0000-0000-0000-000000e20002")
PFMEA_E2E_ID = uuid.UUID("00000000-0000-0000-0000-000000e20100")
CAPA_E2E_ID = uuid.UUID("00000000-0000-0000-0000-000000e20200")


async def _seed_factories(db) -> dict:
    factories = {}
    for code, name, location, fid in [
        (E2E_FACTORY_DC100["code"], E2E_FACTORY_DC100["name"], E2E_FACTORY_DC100["location"], FACT_DC100_ID),
        (E2E_FACTORY_SH["code"], E2E_FACTORY_SH["name"], E2E_FACTORY_SH["location"], FACT_SH_ID),
    ]:
        existing = (await db.execute(select(Factory).where(Factory.code == code))).scalar_one_or_none()
        if not existing:
            db.add(Factory(id=fid, code=code, name=name, location=location, is_active=True))
            await db.flush()
            factories[code] = fid
        else:
            factories[code] = existing.id
    return factories


async def _seed_product_line(db, factory_ids):
    for pl in (E2E_PRODUCT_LINE, E2E_PRODUCT_LINE_DEFAULT):
        existing = (await db.execute(select(ProductLine).where(ProductLine.code == pl["code"]))).scalar_one_or_none()
        if not existing:
            db.add(ProductLine(
                code=pl["code"], name=pl["name"], is_active=True,
                factory_id=factory_ids[E2E_FACTORY_DC100["code"]],
                product_type_code=pl["product_type_code"],
            ))
            await db.flush()


async def _seed_accounts(db, factory_ids):
    roles = {r.role_key: r.id for r in (await db.execute(select(RoleDefinition))).scalars().all()}
    # Non-bypass roles need a UserProductLine assignment or resolve_product_line_scope
    # returns ProductLineScope.NONE → no FMEA/CAPA data visible (factory_scope.py:56).
    # admin/groupadmin have bypass_row_level_security → ProductLineScope.ALL, no assignment needed.
    NON_BYPASS_USERNAMES = {"engineer", "manager", "viewer"}
    for username, password, role_key, factory_codes in E2E_ACCOUNTS:
        user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
        if not user:
            user = User(
                username=username, display_name=username,
                password_hash=hash_password(password), role_id=roles[role_key], is_active=True,
                legacy_role=role_key,
            )
            db.add(user)
            await db.flush()
        # Ensure factory assignments
        existing_facs = {f.factory_id for f in (
            await db.execute(select(UserFactory).where(UserFactory.user_id == user.user_id))
        ).scalars().all()}
        for code in factory_codes:
            fid = factory_ids[code]
            if fid not in existing_facs:
                db.add(UserFactory(user_id=user.user_id, factory_id=fid))
        # Ensure product-line assignment for non-bypass users (so they see FMEA/CAPA data)
        if username in NON_BYPASS_USERNAMES:
            from app.models.role import UserProductLine
            existing_pls = {
                p.product_line_code for p in (
                    await db.execute(select(UserProductLine).where(UserProductLine.user_id == user.user_id))
                ).scalars().all()
            }
            for pl_code in (E2E_PRODUCT_LINE["code"], E2E_PRODUCT_LINE_DEFAULT["code"]):
                if pl_code not in existing_pls:
                    db.add(UserProductLine(user_id=user.user_id, product_line_code=pl_code))


async def _seed_d3_sources(db, factory_id, user_id):
    """Upsert D3 source data: supplier, customer, ERP, IQC, SPC, shipment.

    These are import inputs, not D3 generation tables. Repeated seed updates
    fixed records and does not accumulate duplicates.
    """
    from app.models.customer_quality import Customer, ShipmentRecord
    from app.models.erp import ERPConnection, ERPInventoryBalance, ERPShipment
    from app.models.iqc_inspection import IqcInspection
    from app.models.spc import InspectionCharacteristic, SPCAlarm
    from app.models.supplier import Supplier

    seed_now = datetime.now(timezone.utc)
    seed_date = seed_now.date()

    supplier = await db.scalar(select(Supplier).where(
        Supplier.factory_id == factory_id, Supplier.supplier_no == D3_E2E_SUPPLIER_NO))
    if supplier is None:
        supplier = Supplier(
            supplier_no=D3_E2E_SUPPLIER_NO, factory_id=factory_id,
            name="D3 E2E Supplier", short_name="D3E2E",
            status="approved", created_by=user_id)
        db.add(supplier)
        await db.flush()

    customer = await db.scalar(select(Customer).where(Customer.customer_code == D3_E2E_CUSTOMER_CODE))
    if customer is None:
        customer = Customer(
            customer_code=D3_E2E_CUSTOMER_CODE, name="D3 E2E Key Customer",
            segment=D3_E2E_CUSTOMER_SEGMENT, factory_id=factory_id,
            created_by=user_id)
        db.add(customer)
        await db.flush()
    else:
        customer.name = "D3 E2E Key Customer"
        customer.segment = D3_E2E_CUSTOMER_SEGMENT
        customer.factory_id = factory_id

    connection = await db.scalar(select(ERPConnection).where(
        ERPConnection.name == D3_E2E_ERP_CONNECTION_NAME,
        ERPConnection.factory_id == factory_id))
    if connection is None:
        connection = ERPConnection(
            name=D3_E2E_ERP_CONNECTION_NAME, connector_type="mock",
            config={}, is_active=True,
            product_line_code=D3_E2E_PRODUCT_LINE,
            factory_id=factory_id, created_by=user_id)
        db.add(connection)
        await db.flush()

    inventory = await db.scalar(select(ERPInventoryBalance).where(
        ERPInventoryBalance.connection_id == connection.connection_id,
        ERPInventoryBalance.material_code == D3_E2E_MATERIAL_CODE,
        ERPInventoryBalance.location_code == "D3-E2E-WH-A",
        ERPInventoryBalance.lot_no == D3_E2E_LOT_NO))
    if inventory is None:
        inventory = ERPInventoryBalance(
            connection_id=connection.connection_id, material_code=D3_E2E_MATERIAL_CODE,
            location_code="D3-E2E-WH-A", lot_no=D3_E2E_LOT_NO,
            quantity=120, unit="pcs", inventory_status="quarantine",
            snapshot_at=seed_now,
            product_line_code=D3_E2E_PRODUCT_LINE, factory_id=factory_id,
            erp_raw_data={"seed_key": "d3-e2e-inventory"})
        db.add(inventory)
    else:
        inventory.quantity, inventory.unit, inventory.inventory_status = 120, "pcs", "quarantine"
        inventory.snapshot_at = seed_now

    shipment_record = await db.scalar(select(ShipmentRecord).where(
        ShipmentRecord.customer_id == customer.customer_id,
        ShipmentRecord.product_line_code == D3_E2E_PRODUCT_LINE,
        ShipmentRecord.batch_no == D3_E2E_LOT_NO))
    if shipment_record is None:
        shipment_record = ShipmentRecord(
            customer_id=customer.customer_id, product_line_code=D3_E2E_PRODUCT_LINE,
            factory_id=factory_id, shipment_date=seed_date, quantity=40,
            batch_no=D3_E2E_LOT_NO, destination="E2E destination", created_by=user_id)
        db.add(shipment_record)
        await db.flush()
    else:
        shipment_record.shipment_date = seed_date
        shipment_record.quantity = 40

    shipment = await db.scalar(select(ERPShipment).where(
        ERPShipment.connection_id == connection.connection_id,
        ERPShipment.shipment_number == "D3-SHIP-E2E-001",
        ERPShipment.line_number == "1"))
    shipment_values = dict(
        external_id="D3-SHIP-E2E-001", customer_code=D3_E2E_CUSTOMER_CODE,
        material_code=D3_E2E_MATERIAL_CODE, lot_no=D3_E2E_LOT_NO, quantity=40,
        shipment_date=seed_date, openqms_shipment_id=shipment_record.shipment_id,
        link_status="linked", product_line_code=D3_E2E_PRODUCT_LINE,
        factory_id=factory_id,
        erp_raw_data={"arrival_status": "in_transit", "unit": "pcs",
                      "customer_code": D3_E2E_CUSTOMER_CODE},
    )
    if shipment is None:
        shipment = ERPShipment(
            connection_id=connection.connection_id,
            shipment_number="D3-SHIP-E2E-001", line_number="1",
            **shipment_values)
        db.add(shipment)
    else:
        for key, value in shipment_values.items():
            setattr(shipment, key, value)

    inspection = await db.scalar(select(IqcInspection).where(
        IqcInspection.inspection_no == "IQC-D3-E2E-001"))
    if inspection is None:
        inspection = IqcInspection(
            inspection_no="IQC-D3-E2E-001", supplier_id=supplier.supplier_id,
            part_no=D3_E2E_MATERIAL_CODE, part_name="D3 E2E Material",
            lot_no=D3_E2E_LOT_NO, lot_qty=120, sample_qty=13,
            inspection_result="rejected", defect_qty=2, inspection_date=seed_date,
            status="completed", product_line_code=D3_E2E_PRODUCT_LINE,
            factory_id=factory_id, inspected_by=user_id, judged_by=user_id)
        db.add(inspection)
    else:
        inspection.inspection_result = "rejected"
        inspection.defect_qty = 2
        inspection.inspection_date = seed_date
        inspection.status = "completed"

    characteristic = await db.scalar(select(InspectionCharacteristic).where(
        InspectionCharacteristic.ic_code == "SPC-D3-E2E-001"))
    if characteristic is None:
        characteristic = InspectionCharacteristic(
            ic_code="SPC-D3-E2E-001", product_line=D3_E2E_PRODUCT_LINE,
            factory_id=factory_id, process_name="D3 E2E Process",
            characteristic_name="Output voltage", spec_upper=5.5, spec_lower=4.5,
            target_value=5.0, chart_type="Xbar-R", subgroup_size=5,
            created_by_id=user_id)
        db.add(characteristic)
        await db.flush()
    alarm = await db.scalar(select(SPCAlarm).where(
        SPCAlarm.ic_id == characteristic.ic_id, SPCAlarm.rule_no == 1,
        SPCAlarm.status == "open"))
    if alarm is None:
        db.add(SPCAlarm(
            ic_id=characteristic.ic_id, factory_id=factory_id, rule_no=1,
            triggered_at=seed_now,
            severity="high", status="open"))
    else:
        alarm.triggered_at = seed_now
        alarm.severity = "high"
    await db.flush()


async def _seed_known_docs(db, factory_ids):
    """Create one known PFMEA + one known CAPA for read-flow assertions.

    Model columns verified in app/models/fmea.py and app/models/capa.py:
    - FMEADocument: pk=fmea_id, required non-null: document_no, title, factory_id;
      all other columns have defaults (fmea_type, product_line_code, status, version, …).
    - CAPAEightD: pk=report_id, required non-null: document_no, title, factory_id;
      all other columns have defaults (status='D1_TEAM', severity, …).
    """
    from app.models.fmea import FMEADocument
    from app.models.capa import CAPAEightD

    admin = (await db.execute(select(User).where(User.username == "admin"))).scalar_one()

    pfmea = (await db.execute(select(FMEADocument).where(FMEADocument.document_no == "PFMEA-E2E-001"))).scalar_one_or_none()
    if not pfmea:
        db.add(FMEADocument(
            fmea_id=PFMEA_E2E_ID,
            document_no="PFMEA-E2E-001",
            title="E2E 已知 PFMEA",
            fmea_type="PFMEA",
            product_line_code="DC-DC-100-E2E",
            factory_id=factory_ids[E2E_FACTORY_DC100["code"]],
            status="draft",
            created_by=admin.user_id,
        ))

    capa = (await db.execute(select(CAPAEightD).where(CAPAEightD.document_no == "8D-E2E-001"))).scalar_one_or_none()
    if not capa:
        db.add(CAPAEightD(
            report_id=CAPA_E2E_ID,
            document_no="8D-E2E-001",
            title="E2E 已知 8D",
            product_line_code="DC-DC-100-E2E",
            factory_id=factory_ids[E2E_FACTORY_DC100["code"]],
            created_by=admin.user_id,
        ))


# 7 independent CAPA document numbers for D3 P1-4 status-change tests.
# Each status-transition test gets its own CAPA so advancing one does not break others.
from app.models.capa import CAPAEightD
from app.models.capa_d3 import (
    CapaD3ImportRun,
    CapaD3ContainmentSnapshot,
    CapaD3ImpactReport,
    CapaD3AdviceGeneration,
    CapaD3AiAdvice,
    CapaD3AdviceAdoption,
    CapaD3Execution,
)
from app.services.capa_d3_containment_service import import_containment_data, generate_advice
from app.state_machines.eightd_state import EightDState

D3_CAPA_INITIAL_STATUS = {
    "8D-E2E-D3-001": EightDState.D2_DESCRIPTION,
    "8D-E2E-D3-002": EightDState.D3_INTERIM,
    "8D-E2E-D3-003": EightDState.D3_INTERIM,
    "8D-E2E-D3-004": EightDState.D3_INTERIM,
    "8D-E2E-D3-005": EightDState.D3_INTERIM,
    "8D-E2E-D3-006": EightDState.D3_INTERIM,
    "8D-E2E-D3-007": EightDState.D3_INTERIM,
}

D3_CAPA_NEED_REPORT = [
    "8D-E2E-D3-003",
    "8D-E2E-D3-004",
    "8D-E2E-D3-005",
    "8D-E2E-D3-007",
]

D3_CAPA_NEED_ADVICE = [
    "8D-E2E-D3-007",
]


async def _reset_d3_chain(db, document_no, capa_id):
    """Reset D3 generation chain for an allowlisted E2E CAPA.

    Only usable in a dedicated E2E database: requires E2E_MODE and non-production tenant.
    The caller commits status restoration in the same transaction.
    """
    if not settings.E2E_MODE or settings.TENANT_MODE == "production":
        raise RuntimeError("D3 E2E reset requires E2E_MODE and non-production tenant mode")
    if document_no not in D3_CAPA_INITIAL_STATUS:
        raise ValueError(f"D3 E2E reset document not allowlisted: {document_no}")

    run_ids = [r[0] for r in (await db.execute(select(CapaD3ImportRun.run_id).where(
        CapaD3ImportRun.capa_id == capa_id))).all()]
    if not run_ids:
        return

    report_ids = [r[0] for r in (await db.execute(select(CapaD3ImpactReport.report_id).where(
        CapaD3ImpactReport.run_id.in_(run_ids)))).all()]
    gen_ids = [g[0] for g in (await db.execute(select(CapaD3AdviceGeneration.generation_id).where(
        CapaD3AdviceGeneration.report_id.in_(report_ids)))).all()] if report_ids else []
    advice_ids = [a[0] for a in (await db.execute(select(CapaD3AiAdvice.advice_id).where(
        CapaD3AiAdvice.generation_id.in_(gen_ids)))).all()] if gen_ids else []

    # FK order: adoption → execution → advice → advice_generation → report → snapshot → import_run
    if advice_ids:
        await db.execute(delete(CapaD3AdviceAdoption).where(
            CapaD3AdviceAdoption.advice_id.in_(advice_ids)))
    if report_ids:
        await db.execute(delete(CapaD3Execution).where(
            CapaD3Execution.report_id.in_(report_ids)))
    if advice_ids:
        await db.execute(delete(CapaD3AiAdvice).where(
            CapaD3AiAdvice.advice_id.in_(advice_ids)))
    if report_ids:
        await db.execute(delete(CapaD3AdviceGeneration).where(
            CapaD3AdviceGeneration.report_id.in_(report_ids)))
    await db.execute(delete(CapaD3ImpactReport).where(
        CapaD3ImpactReport.run_id.in_(run_ids)))
    await db.execute(delete(CapaD3ContainmentSnapshot).where(
        CapaD3ContainmentSnapshot.run_id.in_(run_ids)))
    await db.execute(delete(CapaD3ImportRun).where(
        CapaD3ImportRun.capa_id == capa_id))


async def _seed_d3_test_capas(db):
    """Deterministically seed 7 fixed test CAPAs and their D3 fixture state.

    Creates/upserts the 7 CAPAs, resets any existing D3 chain, restores initial
    status, and regenerates done reports/advice where configured.
    """
    from app.seed_e2e_constants import (
        D3_E2E_CAPA_DOC_NO, D3_E2E_CAPA_DOC_NO_CROSSFACTORY,
        D3_E2E_CAPA_DOC_NO_EXEC_FORM, D3_E2E_CAPA_DOC_NO_NOCREDS,
        D3_E2E_CAPA_DOC_NO_REPORTED, D3_E2E_CAPA_DOC_NO_UNIMPORTED,
        D3_E2E_CAPA_DOC_NO_VIEWER,
    )

    user = (await db.execute(select(User).where(User.username == "admin"))).scalar_one()
    dc_factory = (await db.execute(select(Factory).where(
        Factory.code == E2E_FACTORY_DC100["code"]))).scalar_one()

    await _seed_d3_sources(db, dc_factory.id, user.user_id)
    await db.commit()

    # Upsert 7 CAPAs; reset D3 chain and restore initial status.
    for doc_no, initial_status in D3_CAPA_INITIAL_STATUS.items():
        capa = (await db.execute(select(CAPAEightD).where(
            CAPAEightD.document_no == doc_no))).scalar_one_or_none()
        if capa is None:
            capa = CAPAEightD(
                report_id=uuid.uuid4(),
                document_no=doc_no,
                title=f"E2E D3 测试 {doc_no}",
                product_line_code="DC-DC-100-E2E",
                factory_id=dc_factory.id,
                created_by=user.user_id,
            )
            db.add(capa)
            await db.flush()
        await _reset_d3_chain(db, doc_no, capa.report_id)
        await db.execute(update(CAPAEightD).where(
            CAPAEightD.report_id == capa.report_id).values(status=initial_status.value))
        await db.commit()

    # Generate done reports for CAPAs that need them.
    for doc_no in D3_CAPA_NEED_REPORT:
        capa = (await db.execute(select(CAPAEightD).where(
            CAPAEightD.document_no == doc_no))).scalar_one()
        r = await import_containment_data(db, capa.report_id, user, D3ImportRequest())
        if r["report_status"] == "blocked":
            print(f"[d3 seed] {doc_no} report blocked (no LLM credentials)")
            continue
        if r["report_status"] != "done":
            raise RuntimeError(
                f"D3 seed report failed: {doc_no} status={r['report_status']} error={r.get('report_error')}")

        if doc_no in D3_CAPA_NEED_ADVICE:
            report_uuid = uuid.UUID(r["report_id"]) if isinstance(r["report_id"], str) else r["report_id"]
            gen_r = await generate_advice(db, capa.report_id, report_uuid, user, D3AdviceRequest())
            if gen_r["status"] != "done":
                raise RuntimeError(
                    f"D3 seed advice failed: {doc_no} status={gen_r['status']} error={gen_r.get('error')}")


async def main():
    async with async_session() as db:
        factory_ids = await _seed_factories(db)
        await _seed_product_line(db, factory_ids)
        await _seed_accounts(db, factory_ids)
        await _seed_known_docs(db, factory_ids)
        await db.commit()
        await _seed_d3_test_capas(db)
        await db.commit()
    print("E2E seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
