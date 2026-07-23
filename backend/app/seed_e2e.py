"""Deterministic idempotent E2E seed. Run: python -m app.seed_e2e

Idempotent: safe to re-run. Uses -E2E- infix doc numbers so cleanup never touches seed."""
import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select, text, update

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
    DOCGATE_E2E_CAPA_DOC_NO, DOCGATE_E2E_FMEA_DOC_NO, DOCGATE_E2E_CP_DOC_NO,
    DOCGATE_E2E_CP_ID, DOCGATE_E2E_CP_ITEM_ID, DOCGATE_E2E_CP_VER_ID,
    E2E_ACCOUNTS, E2E_FACTORY_DC100, E2E_FACTORY_SH, E2E_PRODUCT_LINE, E2E_PRODUCT_LINE_DEFAULT,
    FMEA_LINK_E2E_CAPA_DOC_NO, FMEA_LINK_E2E_CAPA_SKIPPED_DOC_NO,
    FMEA_LINK_E2E_CAUSE_NODE, FMEA_LINK_E2E_FMEA_DOC_NO,
    FMEA_LINK_E2E_FM_NODE, FMEA_LINK_E2E_PC_NODE,
    KNOWLEDGE_SINK_E2E_CAPA_DOC_NO, KNOWLEDGE_SINK_E2E_CAPA_ID,
    SUPPLIER_RISK_E2E_CAPA_DOC_NO, SUPPLIER_RISK_E2E_CAPA_ID,
    SUPPLIER_RISK_E2E_D7_ACTION_ID, SUPPLIER_RISK_E2E_HIST_CAPA_DOC_NO,
    SUPPLIER_RISK_E2E_HIST_CAPA_ID,
    SCAR_TRIGGER_E2E_CAPA_DOC_NO, SCAR_TRIGGER_E2E_CAPA_ID, SCAR_TRIGGER_E2E_LOT_NO,
    LATERAL_TYPE, LATERAL_PL_SRC, LATERAL_PL_A, LATERAL_PL_B, LATERAL_PL_C, LATERAL_PL_D,
    LATERAL_FM, LATERAL_MATERIAL, LATERAL_CP_CHAR, LATERAL_SUPPLIER_NO,
    LATERAL_E2E_CAPA_001, LATERAL_E2E_CAPA_002, LATERAL_E2E_CAPA_BLOCK, LATERAL_E2E_CAPA_EMPTY,
    LATERAL_E2E_CAPA_001_ID, LATERAL_E2E_CAPA_002_ID, LATERAL_E2E_CAPA_BLOCK_ID,
    LATERAL_E2E_CAPA_EMPTY_ID, LATERAL_E2E_FMEA_SRC, LATERAL_E2E_FMEA_B,
    LATERAL_E2E_CP_SRC, LATERAL_E2E_CP_C,
    D4_AUDIT_E2E_CAPA_DOC_NO, D4_AUDIT_E2E_CAPA_ID,
    D4_AUDIT_E2E_APPROVAL_CAPA_DOC_NO, D4_AUDIT_E2E_APPROVAL_CAPA_ID,
)

# Fixed UUIDs for idempotency
FACT_DC100_ID = uuid.UUID("00000000-0000-0000-0000-000000e20001")
FACT_SH_ID = uuid.UUID("00000000-0000-0000-0000-000000e20002")
PFMEA_E2E_ID = uuid.UUID("00000000-0000-0000-0000-000000e20100")
CAPA_E2E_ID = uuid.UUID("00000000-0000-0000-0000-000000e20200")
DOCGATE_FMEA_ID = uuid.UUID("00000000-0000-0000-0000-000000e20170")
DOCGATE_CAPA_ID = uuid.UUID("00000000-0000-0000-0000-000000e20270")
DOCGATE_FMEA_VER_ID = uuid.UUID("00000000-0000-0000-0000-000000e20171")
DOCGATE_CP_ID = uuid.UUID(DOCGATE_E2E_CP_ID)
DOCGATE_CP_ITEM_ID = uuid.UUID(DOCGATE_E2E_CP_ITEM_ID)
DOCGATE_CP_VER_ID = uuid.UUID(DOCGATE_E2E_CP_VER_ID)
FMEA_LINK_FMEA_ID = uuid.UUID("00000000-0000-0000-0000-000000e20140")
FMEA_LINK_CAPA_ID = uuid.UUID("00000000-0000-0000-0000-000000e20240")
FMEA_LINK_CAPA_SKIPPED_ID = uuid.UUID("00000000-0000-0000-0000-000000e20241")
FMEA_LINK_VERIF_ID = uuid.UUID("00000000-0000-0000-0000-000000e20242")
FMEA_LINK_D7_ID = uuid.UUID("00000000-0000-0000-0000-000000e20243")
FMEA_LINK_D7_SKIPPED_ID = uuid.UUID("00000000-0000-0000-0000-000000e20244")
SCAR_TRIGGER_CAPA_ID = uuid.UUID(SCAR_TRIGGER_E2E_CAPA_ID)
SCAR_TRIGGER_RUN_ID = uuid.UUID("a0000005-0001-4000-8000-000000000002")
SCAR_TRIGGER_REPORT_ID = uuid.UUID("a0000005-0001-4000-8000-000000000003")
KNOWLEDGE_SINK_CAPA_ID = uuid.UUID(KNOWLEDGE_SINK_E2E_CAPA_ID)
SUPPLIER_RISK_CAPA_ID = uuid.UUID(SUPPLIER_RISK_E2E_CAPA_ID)
SUPPLIER_RISK_HIST_CAPA_ID = uuid.UUID(SUPPLIER_RISK_E2E_HIST_CAPA_ID)
SUPPLIER_RISK_D7_ACTION_ID = uuid.UUID(SUPPLIER_RISK_E2E_D7_ACTION_ID)
D4_AUDIT_CAPA_ID = uuid.UUID(D4_AUDIT_E2E_CAPA_ID)
D4_AUDIT_APPROVAL_CAPA_ID = uuid.UUID(D4_AUDIT_E2E_APPROVAL_CAPA_ID)
D4_AUDIT_D7_ID = uuid.UUID("a0000003-0001-4000-8000-000000000003")


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

# Docs allowed to hard-delete D3 generation chains on re-seed (D3 fixtures + 01.5 SCAR).
# Keep SCAR out of D3_CAPA_INITIAL_STATUS so the D3 status/report loop does not own it.
D3_E2E_RESET_ALLOWLIST = frozenset(D3_CAPA_INITIAL_STATUS) | {SCAR_TRIGGER_E2E_CAPA_DOC_NO}


async def _reset_d3_chain(db, document_no, capa_id):
    """Reset D3 generation chain for an allowlisted E2E CAPA.

    Only usable in a dedicated E2E database: requires E2E_MODE and non-production tenant.
    The caller commits status restoration in the same transaction.
    """
    if not settings.E2E_MODE or settings.TENANT_MODE == "production":
        raise RuntimeError("D3 E2E reset requires E2E_MODE and non-production tenant mode")
    if document_no not in D3_E2E_RESET_ALLOWLIST:
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


async def _seed_doc_gate_capa(db, factory_ids):
    """Seed CAPA at D8_GATE_PENDING + FMEA with baseline version (US-E2E-01.7).

    Idempotent: upserts CAPA status to D8_GATE_PENDING and clears prior docg rows
    so re-seed starts from a clean gate state.
    """
    import json
    from datetime import timedelta
    from sqlalchemy import text as sa_text
    from app.models.capa import CAPAEightD
    from app.models.capa_doc_gate import CapaDocgAnalysis, CapaDocgAudit, CapaDocgDecision
    from app.models.fmea import FMEADocument
    from app.models.fmea_version import FMEAVersion
    from app.state_machines.eightd_state import EightDState

    admin = (await db.execute(select(User).where(User.username == "admin"))).scalar_one()
    factory_id = factory_ids[E2E_FACTORY_DC100["code"]]
    product_line = E2E_PRODUCT_LINE["code"]
    snapshot = {
        "nodes": [{"id": "node-1", "type": "ProcessStep", "name": "焊接"}],
        "edges": [],
    }

    fmea = (await db.execute(
        select(FMEADocument).where(FMEADocument.document_no == DOCGATE_E2E_FMEA_DOC_NO)
    )).scalar_one_or_none()
    if not fmea:
        fmea = FMEADocument(
            fmea_id=DOCGATE_FMEA_ID,
            document_no=DOCGATE_E2E_FMEA_DOC_NO,
            title="E2E DocGate PFMEA",
            fmea_type="PFMEA",
            product_line_code=product_line,
            factory_id=factory_id,
            status="approved",
            graph_data=snapshot,
            created_by=admin.user_id,
        )
        db.add(fmea)
        await db.flush()
    else:
        fmea.graph_data = snapshot
        fmea.status = "approved"

    ver = (await db.execute(
        select(FMEAVersion).where(FMEAVersion.version_id == DOCGATE_FMEA_VER_ID)
    )).scalar_one_or_none()
    # fmea_versions has a BEFORE UPDATE OR DELETE trigger (prevent_version_tampering,
    # alembic 020) that RAISEs. Disable it for this re-seed transaction, then re-enable.
    # ALTER TABLE ... DISABLE/ENABLE TRIGGER is transactional in PG.
    await db.execute(text(
        'ALTER TABLE "fmea_versions" DISABLE TRIGGER "trg_fmea_version_no_update"'
    ))
    try:
        # Idempotent re-seed: remove any FMEA versions beyond the baseline created by
        # prior walks (doc-gate audit_run may create new versions). Keeping them would make
        # the gate see a version bump (latest.created_at > capa.created_at) → false PASS/FAIL.
        await db.execute(delete(FMEAVersion).where(
            FMEAVersion.fmea_id == fmea.fmea_id,
            FMEAVersion.version_id != DOCGATE_FMEA_VER_ID,
        ))
        if not ver:
            # Bypass version immutability trigger via direct insert (trigger disabled above
            # is for UPDATE/DELETE; INSERT goes through verify_version_hash, which the raw
            # SQL INSERT with precomputed sha256 satisfies).
            await db.execute(sa_text(
                "INSERT INTO fmea_versions (version_id, fmea_id, factory_id, major_no, minor_no, "
                "snapshot, sha256_hash, change_summary, change_type, created_by, created_at) "
                "VALUES (:vid, :fid, :fact, 1, 0, CAST(:snap AS JSONB), "
                "encode(digest(CAST(:snap AS JSONB)::text, 'sha256'), 'hex'), "
                "'e2e baseline', 'approve', :uid, NOW() - interval '2 days')"
            ), {
                "vid": DOCGATE_FMEA_VER_ID, "fid": fmea.fmea_id, "fact": factory_id,
                "snap": json.dumps(snapshot), "uid": admin.user_id,
            })
        else:
            # Refresh baseline snapshot + factory_id so reseed restores full CANON
            # (prior walks / cross-factory pollution must not leave wrong factory_id).
            await db.execute(sa_text(
                "UPDATE fmea_versions SET factory_id = :fact, "
                "snapshot = CAST(:snap AS JSONB), "
                "sha256_hash = encode(digest(CAST(:snap AS JSONB)::text, 'sha256'), 'hex'), "
                "created_at = NOW() - interval '2 days' WHERE version_id = :vid"
            ), {
                "fact": factory_id,
                "snap": json.dumps(snapshot),
                "vid": DOCGATE_FMEA_VER_ID,
            })
        await db.execute(text(
            'ALTER TABLE "fmea_versions" ENABLE TRIGGER "trg_fmea_version_no_update"'
        ))
        await db.flush()
    except Exception:
        # Re-enable trigger before rollback so a retry starts clean; rollback reverts
        # the disable + any deletes/updates. Do not swallow — re-raise after best-effort enable.
        try:
            await db.execute(text(
                'ALTER TABLE "fmea_versions" ENABLE TRIGGER "trg_fmea_version_no_update"'
            ))
        except Exception:
            pass
        raise


    # Same product-line ControlPlan + baseline version so allowlist can surface CP + FMEA.
    # (01.9 CPs live on LATERAL_* product lines and are invisible to this CAPA's PL filter.)
    from app.models.control_plan import ControlPlan, ControlPlanItem
    from app.models.control_plan_version import ControlPlanVersion

    # Canonical CP header fields (must match version_service.create_cp_version's
    # header_snapshot shape so the baseline diff is empty vs a freshly-reseeded live CP).
    CP_CANON = dict(
        title="E2E DocGate CP",
        status="draft",        # draft (not approved) so update_control_plan allows the
                               # item edit needed for the passed path; approved CPs 400 on PUT.
        phase="production",
        fmea_ref_id=None,
        part_no=None,
        part_name=None,
        contact_info=None,
        drawing_rev=None,
        org_factory=None,
        core_group=None,
    )
    ITEM_CANON = dict(
        step_no="10",
        process_name="定位",
        equipment=None,
        characteristic_no="CP-DOC-001",
        product_characteristic="孔径",
        process_characteristic="定位销磨损检测",
        special_class="CC",
        specification_tolerance=None,
        evaluation_method=None,
        sample_size=None,
        sample_frequency=None,
        control_method="首件+巡检",
        reaction_plan="隔离并换销",
        source_fmea_node_id=None,
        sort_order=0,
    )

    cp = (await db.execute(
        select(ControlPlan).where(ControlPlan.document_no == DOCGATE_E2E_CP_DOC_NO)
    )).scalar_one_or_none()
    if not cp:
        cp = ControlPlan(
            cp_id=DOCGATE_CP_ID,
            document_no=DOCGATE_E2E_CP_DOC_NO,
            product_line_code=product_line,
            factory_id=factory_id,
            created_by=admin.user_id,
            **CP_CANON,
        )
        db.add(cp)
        await db.flush()
        db.add(ControlPlanItem(
            item_id=DOCGATE_CP_ITEM_ID,
            cp_id=cp.cp_id,
            factory_id=factory_id,
            **ITEM_CANON,
        ))
        await db.flush()
    else:
        # Restore full canonical header so live CP == baseline snapshot (phase/fmea_ref_id/
        # part_no etc. included — otherwise a prior walk's edits leave live header != baseline).
        # Also clear approval residue: if a prior walk approved then something else reopened
        # status alone, approved_by/approved_at would still be set while status=draft —
        # that hybrid state confuses approve-path tests and UI.
        cp.product_line_code = product_line
        cp.factory_id = factory_id
        cp.approved_by = None
        cp.approved_at = None
        for k, v in CP_CANON.items():
            setattr(cp, k, v)
        await db.flush()
        # Remove any extra items a prior walk added — baseline has exactly one item, so extra
        # items would show up as phantom "added" rows in the diff.
        await db.execute(delete(ControlPlanItem).where(
            ControlPlanItem.cp_id == cp.cp_id,
            ControlPlanItem.item_id != DOCGATE_CP_ITEM_ID,
        ))
        item = (await db.execute(
            select(ControlPlanItem).where(ControlPlanItem.item_id == DOCGATE_CP_ITEM_ID)
        )).scalar_one_or_none()
        if item is None:
            db.add(ControlPlanItem(
                item_id=DOCGATE_CP_ITEM_ID,
                cp_id=cp.cp_id,
                factory_id=factory_id,
                **ITEM_CANON,
            ))
        else:
            # Reset every field (equipment included — baseline fixes it to None) so the
            # live item matches the baseline item snapshot exactly. Also re-pin factory_id
            # in case a prior import/edit moved the item across factories.
            item.factory_id = factory_id
            for k, v in ITEM_CANON.items():
                setattr(item, k, v)
        await db.flush()

    # CP baseline version (immutable table — disable trigger like FMEA path)
    await db.execute(text(
        'ALTER TABLE "control_plan_versions" DISABLE TRIGGER "trg_cp_version_no_update"'
    ))
    try:
        await db.execute(delete(ControlPlanVersion).where(
            ControlPlanVersion.cp_id == cp.cp_id,
            ControlPlanVersion.version_id != DOCGATE_CP_VER_ID,
        ))
        # Build header_snapshot from the live cp fields (just reset to canonical) so the
        # baseline exactly matches what create_cp_version would snapshot for this CP —
        # includes fmea_ref_id + phase (which version_service includes; a hardcoded subset
        # would make the header diff show spurious changes).
        header_snapshot = {
            "document_no": cp.document_no,
            "title": cp.title,
            "fmea_ref_id": str(cp.fmea_ref_id) if cp.fmea_ref_id else None,
            "product_line_code": cp.product_line_code,
            "status": cp.status,
            "phase": cp.phase,
            "part_no": cp.part_no,
            "part_name": cp.part_name,
            "contact_info": cp.contact_info,
            "drawing_rev": cp.drawing_rev,
            "org_factory": cp.org_factory,
            "core_group": cp.core_group,
        }
        items_snapshot = [{
            "item_id": str(DOCGATE_CP_ITEM_ID),
            **{k: ITEM_CANON[k] for k in (
                "step_no", "process_name", "equipment", "characteristic_no",
                "product_characteristic", "process_characteristic", "special_class",
                "specification_tolerance", "evaluation_method", "sample_size",
                "sample_frequency", "control_method", "reaction_plan",
                "source_fmea_node_id", "sort_order",
            )},
        }]
        cp_ver = (await db.execute(
            select(ControlPlanVersion).where(ControlPlanVersion.version_id == DOCGATE_CP_VER_ID)
        )).scalar_one_or_none()
        if not cp_ver:
            # items_snapshot is a JSON array (version_service shape); hash over
            # {"header": header, "items": items_list} (same as create_cp_version).
            await db.execute(sa_text(
                "INSERT INTO control_plan_versions (version_id, cp_id, factory_id, major_no, minor_no, "
                "header_snapshot, items_snapshot, sha256_hash, change_summary, change_type, "
                "created_by, created_at) "
                "VALUES (:vid, :cid, :fact, 1, 0, CAST(:hdr AS JSONB), CAST(:items AS JSONB), "
                "encode(digest(CAST(:combined AS JSONB)::text, 'sha256'), 'hex'), "
                "'e2e baseline', 'approve', :uid, NOW() - interval '2 days')"
            ), {
                "vid": DOCGATE_CP_VER_ID, "cid": cp.cp_id, "fact": factory_id,
                "hdr": __import__('json').dumps(header_snapshot),
                "items": __import__('json').dumps(items_snapshot),
                "combined": __import__('json').dumps({"header": header_snapshot, "items": items_snapshot}),
                "uid": admin.user_id,
            })
        else:
            await db.execute(sa_text(
                "UPDATE control_plan_versions SET "
                "factory_id = :fact, "
                "header_snapshot = CAST(:hdr AS JSONB), "
                "items_snapshot = CAST(:items AS JSONB), "
                "sha256_hash = encode(digest(CAST(:combined AS JSONB)::text, 'sha256'), 'hex'), "
                "created_at = NOW() - interval '2 days' WHERE version_id = :vid"
            ), {
                "fact": factory_id,
                "hdr": __import__('json').dumps(header_snapshot),
                "items": __import__('json').dumps(items_snapshot),
                "combined": __import__('json').dumps({"header": header_snapshot, "items": items_snapshot}),
                "vid": DOCGATE_CP_VER_ID,
            })
        await db.execute(text(
            'ALTER TABLE "control_plan_versions" ENABLE TRIGGER "trg_cp_version_no_update"'
        ))
        await db.flush()
    except Exception:
        try:
            await db.execute(text(
                'ALTER TABLE "control_plan_versions" ENABLE TRIGGER "trg_cp_version_no_update"'
            ))
        except Exception:
            pass
        raise

    capa = (await db.execute(
        select(CAPAEightD).where(CAPAEightD.document_no == DOCGATE_E2E_CAPA_DOC_NO)
    )).scalar_one_or_none()
    if not capa:
        capa = CAPAEightD(
            report_id=DOCGATE_CAPA_ID,
            document_no=DOCGATE_E2E_CAPA_DOC_NO,
            title="E2E DocGate 8D",
            product_line_code=product_line,
            factory_id=factory_id,
            status=EightDState.D8_GATE_PENDING.value,
            severity="serious",
            d4_root_cause="定位销磨损导致孔径超差",
            d5_correction="更换定位销并校准夹具",
            d7_prevention="将定位销磨损检测纳入首件检验",
            fmea_ref_id=fmea.fmea_id,
            created_by=admin.user_id,
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db.add(capa)
        await db.flush()
    else:
        # Reset status + clear prior doc-gate chain for idempotent re-seed
        analysis_ids = [r[0] for r in (await db.execute(
            select(CapaDocgAnalysis.analysis_id).where(CapaDocgAnalysis.capa_id == capa.report_id)
        )).all()]
        if analysis_ids:
            await db.execute(delete(CapaDocgDecision).where(
                CapaDocgDecision.analysis_id.in_(analysis_ids)))
            await db.execute(delete(CapaDocgAudit).where(
                CapaDocgAudit.analysis_id.in_(analysis_ids)))
            await db.execute(delete(CapaDocgAnalysis).where(
                CapaDocgAnalysis.analysis_id.in_(analysis_ids)))
        # Clear AuditLog for this CAPA — prevents stale DOC_IMPACT_ANALYZED /
        # DOC_UPDATE_AUDITED / DOC_GATE_PASSED / D8_APPROVED from prior walks causing false PASS.
        from app.models.audit import AuditLog as _AuditLog
        await db.execute(delete(_AuditLog).where(_AuditLog.record_id == capa.report_id))
        capa.status = EightDState.D8_GATE_PENDING.value
        # Reset created_at so it stays newer than the baseline version (NOW()-2d).
        # Without this, the fixed baseline (NOW()-2d each reseed) eventually drifts past the
        # stale CAPA created_at (set only on first insert), breaking _get_baseline_version's
        # `version.created_at <= capa.created_at` lookup (capa_doc_gate_service.py).
        capa.created_at = datetime.now(timezone.utc) - timedelta(days=1)
        capa.fmea_ref_id = fmea.fmea_id
        capa.d4_root_cause = "定位销磨损导致孔径超差"
        capa.d5_correction = "更换定位销并校准夹具"
        capa.d7_prevention = "将定位销磨损检测纳入首件检验"
        await db.flush()


async def _seed_fmea_linkage(db, factory_ids):
    """Seed PFMEA + two CAPAs for US-E2E-01.4 bidirectional linkage E2E.

    - PFMEA-E2E-FMEA-LINK-001 with fm-1 / cause-link / pc-link graph
    - 8D-E2E-FMEA-LINK-001 at D4_ROOT_CAUSE with header + D4 source_ref + D7 confirmed
    - 8D-E2E-FMEA-LINK-002 with D7 skipped only (must not appear in reverse lookup)
    - FMEA_LINKAGE_CREATED audits for header / d4_cause / d7_prevention on the first CAPA

    Idempotent on document_no / fixed UUIDs. CASCADE children are deleted+recreated.
    """
    from app.models.audit import AuditLog
    from app.models.capa import CAPAEightD, CapaD7NodeAction, CapaRootCauseVerification
    from app.models.fmea import FMEADocument
    from app.state_machines.eightd_state import EightDState

    admin = (await db.execute(select(User).where(User.username == "admin"))).scalar_one()
    factory_id = factory_ids[E2E_FACTORY_DC100["code"]]
    product_line = E2E_PRODUCT_LINE["code"]
    graph = {
        "nodes": [
            {"id": FMEA_LINK_E2E_FM_NODE, "type": "FailureMode", "name": "孔径超差"},
            {"id": FMEA_LINK_E2E_CAUSE_NODE, "type": "FailureCause", "name": "定位销磨损"},
            {"id": FMEA_LINK_E2E_PC_NODE, "type": "PreventionControl", "name": "定位销周检"},
        ],
        "edges": [
            {
                "source": FMEA_LINK_E2E_CAUSE_NODE,
                "target": FMEA_LINK_E2E_FM_NODE,
                "type": "CAUSE_OF",
            },
            {
                "source": FMEA_LINK_E2E_CAUSE_NODE,
                "target": FMEA_LINK_E2E_PC_NODE,
                "type": "PREVENTED_BY",
            },
        ],
    }
    root_cause = "定位销磨损导致孔径超差（E2E FMEA 联动）"

    fmea = (await db.execute(
        select(FMEADocument).where(FMEADocument.document_no == FMEA_LINK_E2E_FMEA_DOC_NO)
    )).scalar_one_or_none()
    if not fmea:
        fmea = FMEADocument(
            fmea_id=FMEA_LINK_FMEA_ID,
            document_no=FMEA_LINK_E2E_FMEA_DOC_NO,
            title="E2E FMEA 联动 PFMEA",
            fmea_type="PFMEA",
            product_line_code=product_line,
            factory_id=factory_id,
            status="approved",
            graph_data=graph,
            created_by=admin.user_id,
        )
        db.add(fmea)
        await db.flush()
    else:
        fmea.graph_data = graph
        fmea.status = "approved"
        fmea.product_line_code = product_line
        fmea.factory_id = factory_id
        await db.flush()

    source_ref = {
        "fmea_id": str(fmea.fmea_id),
        "cause_node_id": FMEA_LINK_E2E_CAUSE_NODE,
    }

    capa = (await db.execute(
        select(CAPAEightD).where(CAPAEightD.document_no == FMEA_LINK_E2E_CAPA_DOC_NO)
    )).scalar_one_or_none()
    if not capa:
        capa = CAPAEightD(
            report_id=FMEA_LINK_CAPA_ID,
            document_no=FMEA_LINK_E2E_CAPA_DOC_NO,
            title="E2E FMEA 联动 8D",
            product_line_code=product_line,
            factory_id=factory_id,
            status=EightDState.D4_ROOT_CAUSE.value,
            severity="serious",
            d4_root_cause=root_cause,
            d5_correction="更换定位销并校准夹具",
            d7_prevention="将定位销磨损检测纳入首件检验",
            fmea_ref_id=fmea.fmea_id,
            fmea_node_id=FMEA_LINK_E2E_FM_NODE,
            created_by=admin.user_id,
        )
        db.add(capa)
        await db.flush()
    else:
        capa.status = EightDState.D4_ROOT_CAUSE.value
        capa.d4_root_cause = root_cause
        capa.d5_correction = "更换定位销并校准夹具"
        capa.d7_prevention = "将定位销磨损检测纳入首件检验"
        capa.fmea_ref_id = fmea.fmea_id
        capa.fmea_node_id = FMEA_LINK_E2E_FM_NODE
        capa.product_line_code = product_line
        capa.factory_id = factory_id
        await db.flush()

    # Reset D4 verification / D7 actions for idempotent re-seed (CASCADE children)
    await db.execute(delete(CapaRootCauseVerification).where(
        CapaRootCauseVerification.capa_id == capa.report_id))
    await db.execute(delete(CapaD7NodeAction).where(
        CapaD7NodeAction.capa_id == capa.report_id))
    await db.flush()

    db.add(CapaRootCauseVerification(
        verification_id=FMEA_LINK_VERIF_ID,
        capa_id=capa.report_id,
        factory_id=factory_id,
        root_cause_text=root_cause,
        method="measurement",
        result="孔径实测超差，定位销磨损确认",
        is_verified=True,
        conclusion="passed",
        source_ref=source_ref,
        verified_by=admin.user_id,
        verified_at=datetime.now(timezone.utc),
    ))
    db.add(CapaD7NodeAction(
        action_id=FMEA_LINK_D7_ID,
        capa_id=capa.report_id,
        factory_id=factory_id,
        action="confirmed",
        fmea_id=fmea.fmea_id,
        failure_mode_node_id=FMEA_LINK_E2E_FM_NODE,
        failure_cause_node_id=FMEA_LINK_E2E_CAUSE_NODE,
        match_source="linked",
        prevention_control_node_id=FMEA_LINK_E2E_PC_NODE,
        prevention_control_name_before="定位销周检",
        prevention_control_name_after="定位销周检",
        acted_by=admin.user_id,
    ))
    await db.flush()

    # Skipped-only CAPA: must not reverse-lookup via D7
    capa_skip = (await db.execute(
        select(CAPAEightD).where(CAPAEightD.document_no == FMEA_LINK_E2E_CAPA_SKIPPED_DOC_NO)
    )).scalar_one_or_none()
    if not capa_skip:
        capa_skip = CAPAEightD(
            report_id=FMEA_LINK_CAPA_SKIPPED_ID,
            document_no=FMEA_LINK_E2E_CAPA_SKIPPED_DOC_NO,
            title="E2E FMEA 联动 8D（skipped 对照）",
            product_line_code=product_line,
            factory_id=factory_id,
            status=EightDState.D7_PREVENTION.value,
            severity="general",
            d4_root_cause="对照根因（不反查）",
            created_by=admin.user_id,
        )
        db.add(capa_skip)
        await db.flush()
    else:
        capa_skip.status = EightDState.D7_PREVENTION.value
        capa_skip.fmea_ref_id = None
        capa_skip.fmea_node_id = None
        capa_skip.product_line_code = product_line
        capa_skip.factory_id = factory_id
        await db.flush()

    await db.execute(delete(CapaD7NodeAction).where(
        CapaD7NodeAction.capa_id == capa_skip.report_id))
    await db.flush()
    db.add(CapaD7NodeAction(
        action_id=FMEA_LINK_D7_SKIPPED_ID,
        capa_id=capa_skip.report_id,
        factory_id=factory_id,
        action="skipped",
        fmea_id=fmea.fmea_id,
        failure_mode_node_id=FMEA_LINK_E2E_FM_NODE,
        failure_cause_node_id=FMEA_LINK_E2E_CAUSE_NODE,
        match_source="linked",
        reason="E2E skipped control — must not reverse-link",
        acted_by=admin.user_id,
    ))
    await db.flush()

    # Seed FMEA_LINKAGE_CREATED audits (runtime path writes these; seed mirrors for E2E read)
    await db.execute(delete(AuditLog).where(
        AuditLog.record_id == capa.report_id,
        AuditLog.action == "FMEA_LINKAGE_CREATED",
    ))
    for node_id, source in (
        (FMEA_LINK_E2E_FM_NODE, "header"),
        (FMEA_LINK_E2E_CAUSE_NODE, "d4_cause"),
        (FMEA_LINK_E2E_PC_NODE, "d7_prevention"),
    ):
        db.add(AuditLog(
            table_name="capa_eightd",
            record_id=capa.report_id,
            action="FMEA_LINKAGE_CREATED",
            changed_fields={
                "capa_id": str(capa.report_id),
                "fmea_id": str(fmea.fmea_id),
                "node_id": node_id,
                "direction": "8d_to_fmea",
                "source": source,
            },
            operated_by=admin.user_id,
            factory_id=factory_id,
        ))
    await db.flush()


async def _seed_scar_trigger(db, factory_ids):
    """Seed CAPA at D3_INTERIM with current D3 impact report for SCAR trigger E2E.

    Idempotent: upserts CAPA, clears prior scar link, resets D3 chain, and
    inserts a completed current import run + done current impact report with
    lot LOT-E2E-SCAR-001. Relies on D3 E2E supplier from _seed_d3_sources.
    """
    from app.models.capa import CAPAEightD
    from app.models.capa_d3 import CapaD3ImpactReport, CapaD3ImportRun
    from app.models.supplier import SupplierSCAR

    admin = (await db.execute(select(User).where(User.username == "admin"))).scalar_one()
    factory_id = factory_ids[E2E_FACTORY_DC100["code"]]
    product_line = E2E_PRODUCT_LINE["code"]
    now = datetime.now(timezone.utc)

    # Ensure D3 supplier exists (same factory as this CAPA).
    await _seed_d3_sources(db, factory_id, admin.user_id)

    capa = (await db.execute(
        select(CAPAEightD).where(CAPAEightD.document_no == SCAR_TRIGGER_E2E_CAPA_DOC_NO)
    )).scalar_one_or_none()
    if capa is None:
        capa = CAPAEightD(
            report_id=SCAR_TRIGGER_CAPA_ID,
            document_no=SCAR_TRIGGER_E2E_CAPA_DOC_NO,
            title="E2E 8D→SCAR 触发",
            product_line_code=product_line,
            factory_id=factory_id,
            status="D3_INTERIM",
            d2_description="来料外观不良，需向供应商发起 SCAR",
            d3_interim="隔离批次并通知供应商",
            d4_root_cause="供应商工艺偏移",
            created_by=admin.user_id,
        )
        db.add(capa)
        await db.flush()
    else:
        # Drop any previously linked SCAR so re-seed leaves trigger button visible.
        if capa.scar_ref_id is not None:
            linked_scar = await db.get(SupplierSCAR, capa.scar_ref_id)
            capa.scar_ref_id = None
            if linked_scar is not None and linked_scar.capa_ref_id == capa.report_id:
                linked_scar.capa_ref_id = None
                await db.flush()
                await db.delete(linked_scar)
                await db.flush()
        await db.execute(
            update(CAPAEightD)
            .where(CAPAEightD.report_id == capa.report_id)
            .values(
                status="D3_INTERIM",
                title="E2E 8D→SCAR 触发",
                product_line_code=product_line,
                factory_id=factory_id,
                d2_description="来料外观不良，需向供应商发起 SCAR",
                d3_interim="隔离批次并通知供应商",
                d4_root_cause="供应商工艺偏移",
                scar_ref_id=None,
            )
        )
        await db.flush()
        capa = (await db.execute(
            select(CAPAEightD).where(CAPAEightD.document_no == SCAR_TRIGGER_E2E_CAPA_DOC_NO)
        )).scalar_one()

    await _reset_d3_chain(db, SCAR_TRIGGER_E2E_CAPA_DOC_NO, capa.report_id)

    run = CapaD3ImportRun(
        run_id=SCAR_TRIGGER_RUN_ID,
        capa_id=capa.report_id,
        factory_id=factory_id,
        is_current=True,
        status="completed",
        imported_types=["inventory"],
        analysis_context={"risk_mapping_version": "v1", "seed": "scar_trigger"},
        started_at=now,
        completed_at=now,
        imported_by=admin.user_id,
    )
    db.add(run)
    await db.flush()

    report = CapaD3ImpactReport(
        report_id=SCAR_TRIGGER_REPORT_ID,
        run_id=run.run_id,
        factory_id=factory_id,
        is_current=True,
        status="done",
        attempt_token=uuid.uuid4(),
        started_at=now,
        completed_at=now,
        generated_by=admin.user_id,
        stage_runs=[],
        prompt_stats={},
        llm_available=True,
        model="e2e-seed",
        batches=[
            {"material_code": "M1", "lot_no": SCAR_TRIGGER_E2E_LOT_NO},
            {"material_code": "M2", "lot_no": ""},
        ],
        impact_qty={"inventory": 1},
        customer_impact=[],
        time_window={"start": None, "end": None},
        risk_level="medium",
        risk_floor="low",
        risk_explanation="E2E SCAR trigger seed risk",
    )
    db.add(report)
    await db.flush()


async def _seed_knowledge_sink(db, factory_ids):
    """Seed CAPA at D8_APPROVAL_PENDING for US-E2E-01.8 knowledge sink E2E.

    Idempotent: resets status and D-step fields so close can re-trigger sink.
    Does not pre-create knowledge_entries (sink happens on D8 close via LLM).
    """
    from app.models.capa import CAPAEightD
    from app.models.knowledge_entry import KnowledgeEntry
    from app.state_machines.eightd_state import EightDState

    admin = (await db.execute(select(User).where(User.username == "admin"))).scalar_one()
    factory_id = factory_ids[E2E_FACTORY_DC100["code"]]
    product_line = E2E_PRODUCT_LINE["code"]

    capa = (await db.execute(
        select(CAPAEightD).where(CAPAEightD.document_no == KNOWLEDGE_SINK_E2E_CAPA_DOC_NO)
    )).scalar_one_or_none()

    values = dict(
        title="E2E 8D 知识库沉淀",
        product_line_code=product_line,
        factory_id=factory_id,
        status=EightDState.D8_APPROVAL_PENDING.value,
        severity="serious",
        d2_description=(
            "现场抽检一批 DC-DC-100-E2E 来料螺栓，发现 M8 螺栓孔径超差，"
            "实测 8.12mm（上限 8.05mm）。"
        ),
        d3_interim="对该批螺栓 100% 复检隔离，超差件判退供应商。",
        d4_root_cause="定位销磨损导致孔径超差",
        d5_correction="更换定位销并校准夹具，建立定期磨损检测周期。",
        d6_verification="更换后连续 3 批抽检孔径均合格，CPK 1.67。",
        d7_prevention="将定位销磨损检测纳入首件检验 + 周保养点检表。",
        d8_closure="8D 关闭：根因已验证，纠正与预防措施已落地并有效。",
    )

    if capa is None:
        capa = CAPAEightD(
            report_id=KNOWLEDGE_SINK_CAPA_ID,
            document_no=KNOWLEDGE_SINK_E2E_CAPA_DOC_NO,
            created_by=admin.user_id,
            **values,
        )
        db.add(capa)
        await db.flush()
    else:
        await db.execute(
            update(CAPAEightD)
            .where(CAPAEightD.report_id == capa.report_id)
            .values(**values)
        )
        await db.flush()
        capa = (await db.execute(
            select(CAPAEightD).where(CAPAEightD.document_no == KNOWLEDGE_SINK_E2E_CAPA_DOC_NO)
        )).scalar_one()

    # Drop prior sink entry so re-seed starts clean (no CAPA FK; source_id is logical).
    existing_entry = await db.scalar(
        select(KnowledgeEntry).where(
            KnowledgeEntry.source_type == "capa",
            KnowledgeEntry.source_id == capa.report_id,
        )
    )
    if existing_entry is not None:
        await db.execute(
            text(
                """
                UPDATE embedding_sync_outbox
                SET status = 'cancelled'
                WHERE entity_type = 'knowledge_entry'
                  AND entity_id = :id
                  AND status IN ('pending', 'processing')
                """
            ),
            {"id": existing_entry.entry_id},
        )
        await db.execute(
            text(
                "DELETE FROM document_embeddings WHERE entity_type = 'knowledge_entry' AND entity_id = :id"
            ),
            {"id": existing_entry.entry_id},
        )
        await db.delete(existing_entry)
        await db.flush()


async def _seed_supplier_risk_input(db, factory_ids):
    """Seed CAPA at D7_PREVENTION for US-E2E-01.6 supplier risk input E2E.

    - 8D-E2E-RISK-001 at D7_PREVENTION with supplier_id + fmea linkage + D7 action
    - 8D-E2E-RISK-HIST-001 ARCHIVED sibling (same supplier + PL + fmea_node_id)
      so advance detects matched repeat
    - R11/default supplier risk configs (seed_supplier_risk_configs)
    - Clears any prior supplier_risk_capa_inputs for the active CAPA (idempotent)

    Reuses D3-SUP-E2E-001 and PFMEA-E2E-FMEA-LINK-001 graph nodes.
    """
    from app.models.capa import CAPAEightD, CapaD7NodeAction
    from app.models.fmea import FMEADocument
    from app.models.supplier import Supplier
    from app.models.supplier_risk_capa_input import SupplierRiskCapaInput
    from app.seed import seed_supplier_risk_configs
    from app.services.capa_d7_action_service import recommendation_fingerprint
    from app.state_machines.eightd_state import EightDState

    admin = (await db.execute(select(User).where(User.username == "admin"))).scalar_one()
    factory_id = factory_ids[E2E_FACTORY_DC100["code"]]
    product_line = E2E_PRODUCT_LINE["code"]
    root_cause = "定位销磨损导致孔径超差（E2E 供应商风险）"
    prevention = "将定位销磨损检测纳入来料首件检验（E2E 供应商风险）"

    # R11 configs are required for evaluate_supplier_risk_in_tx (worker + confirm-repeat).
    await seed_supplier_risk_configs(db, factory_id)

    await _seed_d3_sources(db, factory_id, admin.user_id)
    supplier = (
        await db.execute(
            select(Supplier).where(
                Supplier.factory_id == factory_id,
                Supplier.supplier_no == D3_E2E_SUPPLIER_NO,
            )
        )
    ).scalar_one()

    fmea = (
        await db.execute(
            select(FMEADocument).where(FMEADocument.document_no == FMEA_LINK_E2E_FMEA_DOC_NO)
        )
    ).scalar_one_or_none()
    if fmea is None:
        # _seed_fmea_linkage should have run first; create minimal graph if not.
        graph = {
            "nodes": [
                {"id": FMEA_LINK_E2E_FM_NODE, "type": "FailureMode", "name": "孔径超差"},
                {"id": FMEA_LINK_E2E_CAUSE_NODE, "type": "FailureCause", "name": "定位销磨损"},
                {"id": FMEA_LINK_E2E_PC_NODE, "type": "PreventionControl", "name": "定位销周检"},
            ],
            "edges": [
                {
                    "source": FMEA_LINK_E2E_CAUSE_NODE,
                    "target": FMEA_LINK_E2E_FM_NODE,
                    "type": "CAUSE_OF",
                },
                {
                    "source": FMEA_LINK_E2E_CAUSE_NODE,
                    "target": FMEA_LINK_E2E_PC_NODE,
                    "type": "PREVENTED_BY",
                },
            ],
        }
        fmea = FMEADocument(
            fmea_id=FMEA_LINK_FMEA_ID,
            document_no=FMEA_LINK_E2E_FMEA_DOC_NO,
            title="E2E FMEA 联动 PFMEA",
            fmea_type="PFMEA",
            product_line_code=product_line,
            factory_id=factory_id,
            status="approved",
            graph_data=graph,
            created_by=admin.user_id,
        )
        db.add(fmea)
        await db.flush()

    # Historical ARCHIVED CAPA — same supplier + PL + fmea_node for matched repeat.
    hist = (
        await db.execute(
            select(CAPAEightD).where(CAPAEightD.document_no == SUPPLIER_RISK_E2E_HIST_CAPA_DOC_NO)
        )
    ).scalar_one_or_none()
    if hist is None:
        hist = CAPAEightD(
            report_id=SUPPLIER_RISK_HIST_CAPA_ID,
            document_no=SUPPLIER_RISK_E2E_HIST_CAPA_DOC_NO,
            title="E2E 供应商风险 8D（历史归档）",
            product_line_code=product_line,
            factory_id=factory_id,
            status=EightDState.ARCHIVED.value,
            severity="serious",
            d4_root_cause="历史根因：定位销磨损",
            d7_prevention="历史预防措施",
            fmea_ref_id=fmea.fmea_id,
            fmea_node_id=FMEA_LINK_E2E_FM_NODE,
            supplier_id=supplier.supplier_id,
            created_by=admin.user_id,
        )
        db.add(hist)
        await db.flush()
    else:
        hist.status = EightDState.ARCHIVED.value
        hist.product_line_code = product_line
        hist.factory_id = factory_id
        hist.fmea_ref_id = fmea.fmea_id
        hist.fmea_node_id = FMEA_LINK_E2E_FM_NODE
        hist.supplier_id = supplier.supplier_id
        hist.severity = "serious"
        await db.flush()

    # Active CAPA at D7_PREVENTION ready to advance → D7_COMPLETED.
    capa = (
        await db.execute(
            select(CAPAEightD).where(CAPAEightD.document_no == SUPPLIER_RISK_E2E_CAPA_DOC_NO)
        )
    ).scalar_one_or_none()
    if capa is None:
        capa = CAPAEightD(
            report_id=SUPPLIER_RISK_CAPA_ID,
            document_no=SUPPLIER_RISK_E2E_CAPA_DOC_NO,
            title="E2E 8D→供应商风险输入",
            product_line_code=product_line,
            factory_id=factory_id,
            status=EightDState.D7_PREVENTION.value,
            severity="serious",
            d2_description="来料不良涉及供应商，需写入供应商风险输入",
            d4_root_cause=root_cause,
            d5_correction="更换定位销并校准夹具",
            d6_verification="措施已验证有效",
            d7_prevention=prevention,
            fmea_ref_id=fmea.fmea_id,
            fmea_node_id=FMEA_LINK_E2E_FM_NODE,
            supplier_id=supplier.supplier_id,
            created_by=admin.user_id,
        )
        db.add(capa)
        await db.flush()
    else:
        capa.status = EightDState.D7_PREVENTION.value
        capa.title = "E2E 8D→供应商风险输入"
        capa.product_line_code = product_line
        capa.factory_id = factory_id
        capa.severity = "serious"
        capa.d2_description = "来料不良涉及供应商，需写入供应商风险输入"
        capa.d4_root_cause = root_cause
        capa.d5_correction = "更换定位销并校准夹具"
        capa.d6_verification = "措施已验证有效"
        capa.d7_prevention = prevention
        capa.fmea_ref_id = fmea.fmea_id
        capa.fmea_node_id = FMEA_LINK_E2E_FM_NODE
        capa.supplier_id = supplier.supplier_id
        await db.flush()

    # Clear prior risk inputs so re-seed leaves a clean pending path after advance.
    await db.execute(
        delete(SupplierRiskCapaInput).where(SupplierRiskCapaInput.capa_id == capa.report_id)
    )
    await db.execute(
        delete(CapaD7NodeAction).where(CapaD7NodeAction.capa_id == capa.report_id)
    )
    await db.flush()

    # Canonical hash must match get_d7_recommendations linked rec for gate pass.
    rec_hash = recommendation_fingerprint(
        fmea_id=fmea.fmea_id,
        failure_mode_node_id=FMEA_LINK_E2E_FM_NODE,
        failure_cause_node_id=FMEA_LINK_E2E_CAUSE_NODE,
        failure_mode_name="孔径超差",
        failure_cause_name="定位销磨损",
        match_reason="关联FMEA失效模式",
        prevention_control_node_id=FMEA_LINK_E2E_PC_NODE,
        prevention_control_name="定位销周检",
    )
    db.add(
        CapaD7NodeAction(
            action_id=SUPPLIER_RISK_D7_ACTION_ID,
            capa_id=capa.report_id,
            factory_id=factory_id,
            action="confirmed",
            fmea_id=fmea.fmea_id,
            failure_mode_node_id=FMEA_LINK_E2E_FM_NODE,
            failure_cause_node_id=FMEA_LINK_E2E_CAUSE_NODE,
            match_source="linked",
            prevention_control_node_id=FMEA_LINK_E2E_PC_NODE,
            prevention_control_name_before="定位销周检",
            prevention_control_name_after="定位销周检",
            recommendation_hash=rec_hash,
            acted_by=admin.user_id,
        )
    )
    await db.flush()


async def _seed_lateral_diffusion(db, factory_ids):
    """US-E2E-01.9: four CAPAs + shared PL/FMEA/CP/IQC fixtures for lateral diffusion."""
    from app.models.capa import CAPAEightD
    from app.models.capa_d3 import CapaD3ImpactReport, CapaD3ImportRun
    from app.models.control_plan import ControlPlan, ControlPlanItem
    from app.models.fmea import FMEADocument
    from app.models.iqc_inspection import IqcInspection
    from app.models.iqc_material import IqcMaterial
    from app.models.product_line import ProductLine
    from app.models.product_type import ProductType
    from app.models.role import UserProductLine
    from app.models.supplier import Supplier
    from app.state_machines.eightd_state import EightDState

    admin = (await db.execute(select(User).where(User.username == "admin"))).scalar_one()
    engineer = (await db.execute(select(User).where(User.username == "engineer"))).scalar_one()
    manager = (await db.execute(select(User).where(User.username == "manager"))).scalar_one()
    factory_id = factory_ids[E2E_FACTORY_DC100["code"]]

    # product type
    if not await db.scalar(select(ProductType).where(ProductType.code == LATERAL_TYPE)):
        db.add(ProductType(code=LATERAL_TYPE, name="Lateral E2E Type", is_active=True))
        await db.flush()

    # product lines
    for code, ptype in [
        (LATERAL_PL_SRC, LATERAL_TYPE),
        (LATERAL_PL_A, LATERAL_TYPE),
        (LATERAL_PL_B, "TYPE-LAT-B"),
        (LATERAL_PL_C, "TYPE-LAT-C"),
        (LATERAL_PL_D, "TYPE-LAT-D"),
    ]:
        if ptype != LATERAL_TYPE and not await db.scalar(select(ProductType).where(ProductType.code == ptype)):
            db.add(ProductType(code=ptype, name=ptype, is_active=True))
            await db.flush()
        existing = await db.scalar(select(ProductLine).where(ProductLine.code == code))
        if existing is None:
            db.add(ProductLine(code=code, name=code, factory_id=factory_id, product_type_code=ptype, is_active=True))
        else:
            existing.product_type_code = ptype
            existing.factory_id = factory_id
            existing.is_active = True
    await db.flush()

    # recipients: engineer/manager on PL-A..D
    for u in (engineer, manager):
        for pl in (LATERAL_PL_A, LATERAL_PL_B, LATERAL_PL_C, LATERAL_PL_D):
            exists = await db.scalar(
                select(UserProductLine).where(
                    UserProductLine.user_id == u.user_id,
                    UserProductLine.product_line_code == pl,
                )
            )
            if not exists:
                db.add(UserProductLine(id=uuid.uuid4(), user_id=u.user_id, product_line_code=pl))
    await db.flush()

    # supplier
    sup = await db.scalar(select(Supplier).where(Supplier.supplier_no == LATERAL_SUPPLIER_NO, Supplier.factory_id == factory_id))
    if sup is None:
        sup = Supplier(
            supplier_id=uuid.uuid4(),
            supplier_no=LATERAL_SUPPLIER_NO,
            factory_id=factory_id,
            name="Lateral E2E Supplier",
            short_name="LAT-SUP",
            created_by=admin.user_id,
        )
        db.add(sup)
        await db.flush()

    # FMEA src + B
    async def _ensure_fmea(doc_no, pl, status="approved"):
        f = await db.scalar(select(FMEADocument).where(FMEADocument.document_no == doc_no))
        graph = {"nodes": [{"id": "fm-lat", "type": "FailureMode", "name": LATERAL_FM}], "edges": []}
        if f is None:
            f = FMEADocument(
                fmea_id=uuid.uuid4(), document_no=doc_no, title=doc_no, fmea_type="PFMEA",
                product_line_code=pl, factory_id=factory_id, status=status,
                created_by=admin.user_id, graph_data=graph,
            )
            db.add(f)
        else:
            f.product_line_code = pl
            f.status = status
            f.graph_data = graph
            f.factory_id = factory_id
        await db.flush()
        return f

    fmea_src = await _ensure_fmea(LATERAL_E2E_FMEA_SRC, LATERAL_PL_SRC)
    await _ensure_fmea(LATERAL_E2E_FMEA_B, LATERAL_PL_B)

    # CP src + C
    async def _ensure_cp(doc_no, pl):
        cp = await db.scalar(select(ControlPlan).where(ControlPlan.document_no == doc_no))
        if cp is None:
            cp = ControlPlan(
                cp_id=uuid.uuid4(), document_no=doc_no, title=doc_no,
                product_line_code=pl, factory_id=factory_id, status="approved",
                created_by=admin.user_id,
            )
            db.add(cp)
            await db.flush()
            db.add(ControlPlanItem(
                item_id=uuid.uuid4(), cp_id=cp.cp_id, step_no="10",
                characteristic_no=LATERAL_CP_CHAR, product_characteristic="lat-thick",
                process_characteristic="lat-press", special_class="CC",
                factory_id=factory_id, sort_order=0,
            ))
        else:
            cp.product_line_code = pl
            cp.status = "approved"
            cp.factory_id = factory_id
        await db.flush()
        return cp

    await _ensure_cp(LATERAL_E2E_CP_SRC, LATERAL_PL_SRC)
    await _ensure_cp(LATERAL_E2E_CP_C, LATERAL_PL_C)

    # IQC material + inspection on PL-D
    mat = await db.scalar(select(IqcMaterial).where(IqcMaterial.part_no == LATERAL_MATERIAL))
    if mat is None:
        mat = IqcMaterial(
            material_id=uuid.uuid4(), part_no=LATERAL_MATERIAL, part_name="Lat Mat",
            product_line_code=LATERAL_PL_D, factory_id=factory_id, status="active",
            created_by=admin.user_id,
        )
        db.add(mat)
        await db.flush()
    insp = await db.scalar(select(IqcInspection).where(IqcInspection.inspection_no == "IQC-E2E-LATERAL-001"))
    if insp is None:
        db.add(IqcInspection(
            inspection_id=uuid.uuid4(), inspection_no="IQC-E2E-LATERAL-001",
            supplier_id=sup.supplier_id, part_no=LATERAL_MATERIAL, material_id=mat.material_id,
            product_line_code=LATERAL_PL_D, factory_id=factory_id,
            inspection_result="accepted", status="completed",
        ))
        await db.flush()

    # four CAPAs at D8_APPROVAL_PENDING
    capa_specs = [
        (LATERAL_E2E_CAPA_001, LATERAL_E2E_CAPA_001_ID, True, "E2E 横向扩散通知"),
        (LATERAL_E2E_CAPA_002, LATERAL_E2E_CAPA_002_ID, True, "E2E 横向扩散跳过"),
        (LATERAL_E2E_CAPA_BLOCK, LATERAL_E2E_CAPA_BLOCK_ID, True, "E2E 横向扩散阻塞"),
        (LATERAL_E2E_CAPA_EMPTY, LATERAL_E2E_CAPA_EMPTY_ID, False, "E2E 横向扩散空命中"),
    ]
    for doc_no, cid, with_hits, title in capa_specs:
        capa_id = uuid.UUID(cid)
        capa = await db.scalar(select(CAPAEightD).where(CAPAEightD.document_no == doc_no))
        pl = LATERAL_PL_SRC if with_hits else "DC-DC-100-E2E"
        values = dict(
            title=title,
            product_line_code=pl,
            factory_id=factory_id,
            status=EightDState.D8_APPROVAL_PENDING.value,
            severity="serious",
            supplier_id=sup.supplier_id if with_hits else None,
            fmea_ref_id=fmea_src.fmea_id if with_hits else None,
            d2_description="横向扩散 E2E 问题描述",
            d3_interim="临时围堵",
            d4_root_cause="定位销磨损导致孔径超差",
            d5_correction="更换定位销",
            d6_verification="已验证",
            d7_prevention="周检",
            d8_closure="准备关闭",
            d1_team=[],
        )
        if capa is None:
            capa = CAPAEightD(report_id=capa_id, document_no=doc_no, created_by=admin.user_id, **values)
            db.add(capa)
            await db.flush()
        else:
            await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == capa.report_id).values(**values))
            await db.flush()
            capa = await db.scalar(select(CAPAEightD).where(CAPAEightD.document_no == doc_no))

        if with_hits:
            # D3 current done report with material batch
            run = await db.scalar(
                select(CapaD3ImportRun).where(
                    CapaD3ImportRun.capa_id == capa.report_id,
                    CapaD3ImportRun.is_current.is_(True),
                )
            )
            if run is None:
                run = CapaD3ImportRun(
                    run_id=uuid.uuid4(), capa_id=capa.report_id, factory_id=factory_id,
                    is_current=True, status="completed", imported_types=["iqc"],
                    analysis_context={}, completed_at=datetime.now(timezone.utc),
                    imported_by=admin.user_id,
                )
                db.add(run)
                await db.flush()
            rpt = await db.scalar(
                select(CapaD3ImpactReport).where(
                    CapaD3ImpactReport.run_id == run.run_id,
                    CapaD3ImpactReport.is_current.is_(True),
                )
            )
            if rpt is None:
                db.add(CapaD3ImpactReport(
                    report_id=uuid.uuid4(), run_id=run.run_id, factory_id=factory_id,
                    is_current=True, status="done",
                    batches=[{"material_code": LATERAL_MATERIAL, "lot_no": "LOT-LAT-1"}],
                    impact_qty={"total": 1}, customer_impact=[],
                    time_window={"start": "2026-01-01", "end": "2026-01-31"},
                    risk_level="medium", risk_floor="low",
                    risk_explanation="e2e lateral risk", llm_available=True,
                    completed_at=datetime.now(timezone.utc), generated_by=admin.user_id,
                    attempt_token=uuid.uuid4(),
                ))
                await db.flush()


async def _seed_d4_audit(db, factory_ids):
    """US-E2E-01.3: dedicated pre-gate CAPA + approval rejection CAPA.

    - 8D-E2E-D4-001 at D4_ROOT_CAUSE — 01.3 pre-gate drives D4 verify → D7 action → D8_GATE_PENDING.
      Links to PFMEA-E2E-FMEA-LINK-001 (created by _seed_fmea_linkage, runs before this).
      No pre-existing D4 verifications or D7 node-actions — 01.3 walk creates them fresh.
    - 8D-E2E-APPROVAL-001 at D8_APPROVAL_PENDING — 01.3 post-gate rejection path (approve path
      uses 8D-E2E-DOCGATE-001 from 01.7). Not consumed by any other sub-story.

    Idempotent on document_no / fixed UUIDs.
    """
    from app.models.audit import AuditLog
    from app.models.capa import CAPAEightD, CapaD7NodeAction, CapaRootCauseVerification
    from app.models.fmea import FMEADocument
    from app.state_machines.eightd_state import EightDState

    admin = (await db.execute(select(User).where(User.username == "admin"))).scalar_one()
    factory_id = factory_ids[E2E_FACTORY_DC100["code"]]
    product_line = E2E_PRODUCT_LINE["code"]

    # Ensure FMEA exists (created by _seed_fmea_linkage; read back for fmea_id)
    fmea = (await db.execute(
        select(FMEADocument).where(FMEADocument.document_no == FMEA_LINK_E2E_FMEA_DOC_NO)
    )).scalar_one_or_none()
    if not fmea:
        raise RuntimeError(
            f"{FMEA_LINK_E2E_FMEA_DOC_NO} 不存在——_seed_d4_audit 必须在 _seed_fmea_linkage 之后运行"
        )

    root_cause = "定位销磨损导致孔径超差（E2E 01.3 验收）"

    # ── 8D-E2E-D4-001: D4_ROOT_CAUSE for pre-gate ──
    capa = (await db.execute(
        select(CAPAEightD).where(CAPAEightD.document_no == D4_AUDIT_E2E_CAPA_DOC_NO)
    )).scalar_one_or_none()
    if not capa:
        capa = CAPAEightD(
            report_id=D4_AUDIT_CAPA_ID,
            document_no=D4_AUDIT_E2E_CAPA_DOC_NO,
            title="E2E 01.3 验收 8D（D4→gate）",
            product_line_code=product_line,
            factory_id=factory_id,
            status=EightDState.D4_ROOT_CAUSE.value,
            severity="serious",
            d1_team=[{"name": "E2E 验证", "role": "质量工程师"}],
            d2_description="孔径超差投诉（E2E 01.3 验收）",
            d3_interim="隔离受影响批次",
            d4_root_cause=root_cause,
            d5_correction="更换定位销并校准夹具",
            d6_verification="首件检验确认孔径合格",
            d7_prevention="将定位销磨损检测纳入首件检验",
            fmea_ref_id=fmea.fmea_id,
            created_by=admin.user_id,
        )
        db.add(capa)
        await db.flush()
    else:
        capa.status = EightDState.D4_ROOT_CAUSE.value
        capa.d4_root_cause = root_cause
        capa.d5_correction = "更换定位销并校准夹具"
        capa.d6_verification = "首件检验确认孔径合格"
        capa.d7_prevention = "将定位销磨损检测纳入首件检验"
        capa.fmea_ref_id = fmea.fmea_id
        capa.product_line_code = product_line
        capa.factory_id = factory_id
        await db.flush()

    # Idempotent cleanup: remove any stale D4 verifications / D7 actions so 01.3 starts clean
    await db.execute(delete(CapaRootCauseVerification).where(
        CapaRootCauseVerification.capa_id == capa.report_id))
    await db.execute(delete(CapaD7NodeAction).where(
        CapaD7NodeAction.capa_id == capa.report_id))
    await db.flush()

    # Clean up stale audit records for both CAPAs (prevents false PASS from prior-walk residuals)
    for _capa_id in [capa.report_id, D4_AUDIT_APPROVAL_CAPA_ID]:
        await db.execute(delete(AuditLog).where(AuditLog.record_id == _capa_id))
    await db.flush()

    # ── 8D-E2E-APPROVAL-001: D8_APPROVAL_PENDING for post-gate rejection ──
    capa_rej = (await db.execute(
        select(CAPAEightD).where(CAPAEightD.document_no == D4_AUDIT_E2E_APPROVAL_CAPA_DOC_NO)
    )).scalar_one_or_none()
    if not capa_rej:
        capa_rej = CAPAEightD(
            report_id=D4_AUDIT_APPROVAL_CAPA_ID,
            document_no=D4_AUDIT_E2E_APPROVAL_CAPA_DOC_NO,
            title="E2E 01.3 审批驳回 8D",
            product_line_code=product_line,
            factory_id=factory_id,
            status=EightDState.D8_APPROVAL_PENDING.value,
            severity="general",
            d1_team=[{"name": "E2E 审批人", "role": "质量经理"}],
            d2_description="驳回验收 CAPA（E2E 01.3）",
            d3_interim="临时措施已完成",
            d4_root_cause="测试根因（审批驳回验收）",
            d5_correction="测试纠正措施",
            d6_verification="测试验证",
            d7_prevention="测试预防措施",
            d8_closure="待审批",
            created_by=admin.user_id,
        )
        db.add(capa_rej)
        await db.flush()
    else:
        capa_rej.status = EightDState.D8_APPROVAL_PENDING.value
        capa_rej.product_line_code = product_line
        capa_rej.factory_id = factory_id
        await db.flush()


async def main():
    async with async_session() as db:
        factory_ids = await _seed_factories(db)
        await _seed_product_line(db, factory_ids)
        await _seed_accounts(db, factory_ids)
        await _seed_known_docs(db, factory_ids)
        await _seed_doc_gate_capa(db, factory_ids)
        await _seed_fmea_linkage(db, factory_ids)
        await _seed_d4_audit(db, factory_ids)
        await db.commit()
        await _seed_d3_test_capas(db)
        await _seed_scar_trigger(db, factory_ids)
        await _seed_knowledge_sink(db, factory_ids)
        await _seed_supplier_risk_input(db, factory_ids)
        await _seed_lateral_diffusion(db, factory_ids)
        await db.commit()
    print("E2E seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
