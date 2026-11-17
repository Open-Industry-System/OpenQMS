"""Persisted-state regressions for precommit SC scope enforcement."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.core.factory_scope import FactoryScope, ProductLineScope
from app.models.special_characteristic import SpecialCharacteristic
from app.schemas.special_characteristic import SCUpdate, SafetySubmitRequest, SafetyApprovalAction
from app.services import special_characteristic_service as service


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["update", "msa", "submit", "approve", "reject", "confirm", "dismiss", "cancel"])
async def test_denied_characteristic_mutation_leaves_persisted_state(db, default_factory, operation):
    original_status = "submitted" if operation in ("approve", "reject") else "approved" if operation == "cancel" else "pending"
    sc = SpecialCharacteristic(sc_code="SEC-" + uuid.uuid4().hex[:16], sc_name="original", sc_type="SC",
                               source_node_id="", source_type="PFMEA", product_line_code="sibling",
                               factory_id=default_factory.id, safety_approval_status=original_status,
                               is_safety_suggested=operation in ("confirm", "dismiss"))
    db.add(sc)
    await db.flush()
    request_scope = SimpleNamespace(user=SimpleNamespace(user_id=uuid.uuid4()),
                                    effective_factory_id=default_factory.id,
                                    factory_scope=FactoryScope([default_factory.id], default_factory.id),
                                    pl_scope=ProductLineScope("EXPLICIT", ["allowed"]))
    with patch("app.core.permissions.get_user_permission", AsyncMock(return_value=5)):
        with pytest.raises(HTTPException) as error:
            if operation == "update":
                await service.update_special_characteristic(db, sc.sc_id, SCUpdate(sc_name="changed"), request_scope.user.user_id, scope=request_scope)
            elif operation == "msa":
                await service.update_msa_status(db, sc.sc_id, 40, scope=request_scope)
            elif operation == "submit":
                await service.safety_submit(db, sc.sc_id, SafetySubmitRequest(safety_regulation_ref="rule", safety_verification_method="test"), request_scope.user.user_id, scope=request_scope)
            elif operation in ("approve", "reject"):
                await getattr(service, "safety_" + operation)(db, sc.sc_id, SafetyApprovalAction(comment="test"), request_scope.user.user_id, scope=request_scope)
            else:
                await getattr(service, "safety_" + operation)(db, sc.sc_id, request_scope.user.user_id, scope=request_scope)
    assert error.value.status_code == 404
    await db.refresh(sc)
    assert sc.sc_name == "original"
    assert sc.msa_status == "PENDING"
    assert sc.safety_approval_status == original_status


def restricted_scope(user, factory_id, codes=None, mode="EXPLICIT"):
    return SimpleNamespace(user=user, effective_factory_id=factory_id,
                           factory_scope=FactoryScope([factory_id], factory_id),
                           pl_scope=ProductLineScope(mode, codes or ["not-assigned"]))


@pytest.mark.asyncio
@pytest.mark.parametrize("document", ["fmea", "cp"])
async def test_history_denies_persisted_parent_outside_line(db, admin_user, default_factory, document):
    from app.models.fmea import FMEADocument
    from app.models.control_plan import ControlPlan
    from app.api import version
    if document == "fmea":
        parent = FMEADocument(document_no=uuid.uuid4().hex, title="secret", product_line_code="DC-DC-100", factory_id=default_factory.id)
        fn, ident = version.get_fmea_version_detail, "fmea_id"
    else:
        parent = ControlPlan(document_no=uuid.uuid4().hex, title="secret", product_line_code="DC-DC-100", factory_id=default_factory.id, created_by=admin_user.user_id)
        fn, ident = version.get_cp_version_detail, "cp_id"
    db.add(parent)
    await db.flush()
    from app.services import version_service
    create = version_service.create_fmea_version if document == "fmea" else version_service.create_cp_version
    version = await create(db, parent, "manual", "confidential snapshot", admin_user.user_id)
    with patch("app.core.permissions.get_user_permission", AsyncMock(return_value=5)):
        with pytest.raises(HTTPException) as error:
            await fn(**{ident: getattr(parent, ident), "major": version.major_no, "minor": version.minor_no, "db": db, "scope": restricted_scope(admin_user, default_factory.id)})
    assert error.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("module", ["erp", "plm"])
async def test_persisted_integration_sibling_denied_before_update(db, admin_user, default_factory, module):
    from importlib import import_module
    api = import_module("app.api." + module)
    model = getattr(import_module("app.models." + module), module.upper() + "Connection")
    schema = import_module("app.schemas." + module)
    connection = model(name="original", connector_type="mock", product_line_code="DC-DC-100", factory_id=default_factory.id, created_by=admin_user.user_id)
    db.add(connection)
    await db.flush()
    data = getattr(schema, module.upper() + "ConnectionUpdate")(name="changed")
    with patch.object(api, "get_user_permission", AsyncMock(return_value=5)):
        with pytest.raises(HTTPException) as error:
            args = {"connection_id": connection.connection_id, "db": db, "scope": restricted_scope(admin_user, default_factory.id)}
            args["data" if module == "erp" else "req"] = data
            await api.update_connection(**args)
    assert error.value.status_code == 404
    await db.refresh(connection)
    assert connection.name == "original"


@pytest.mark.asyncio
async def test_risk_snapshots_inherit_supplier_factory_and_line(db, admin_user, default_factory):
    from app.models.factory import Factory
    from app.models.supplier import Supplier
    from app.models.supply_chain_risk_map import SupplyChainRiskSnapshot
    from app.services.supply_chain_risk_map import service
    other = Factory(code="SEC-" + uuid.uuid4().hex[:12], name="other")
    db.add(other)
    await db.flush()
    suppliers = [Supplier(supplier_no=uuid.uuid4().hex, name="visible", short_name="V", created_by=admin_user.user_id, factory_id=default_factory.id),
                 Supplier(supplier_no=uuid.uuid4().hex, name="secret", short_name="S", created_by=admin_user.user_id, factory_id=other.id)]
    db.add_all(suppliers)
    await db.flush()
    for supplier in suppliers:
        db.add(SupplyChainRiskSnapshot(supplier_id=supplier.supplier_id, product_line_code="DC-DC-100", snapshot_period=service.current_period(), risk_score=10, risk_level="low", dimensions={}))
    await db.flush()
    sc = restricted_scope(admin_user, default_factory.id, ["DC-DC-100"])
    heatmap = await service.get_heatmap_data(db, "DC-DC-100", None, scope=sc)
    assert [row.supplier_id for row in heatmap.rows] == [suppliers[0].supplier_id]
    sc.pl_scope = ProductLineScope("NONE", None)
    assert not (await service.get_heatmap_data(db, "DC-DC-100", None, scope=sc)).rows


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["erp", "plm"])
async def test_integration_child_list_and_direct_parent_parity(db, admin_user, default_factory, kind):
    from importlib import import_module
    from sqlalchemy import select
    from app.core.factory_scope import apply_integration_scope
    from app.models.product_line import ProductLine
    models = import_module("app.models." + kind)
    api = import_module("app.api." + kind)
    parent_model = getattr(models, kind.upper() + "Connection")
    child_model = getattr(models, "ERPSupplier" if kind == "erp" else "PLMPart")
    sibling = "SEC-" + uuid.uuid4().hex[:12]
    db.add(ProductLine(code=sibling, name="sibling", factory_id=default_factory.id))
    await db.flush()
    parents = [parent_model(name="allowed", connector_type="mock", product_line_code="DC-DC-100", factory_id=default_factory.id, created_by=admin_user.user_id),
               parent_model(name="sibling", connector_type="mock", product_line_code=sibling, factory_id=default_factory.id, created_by=admin_user.user_id)]
    db.add_all(parents)
    await db.flush()
    children = []
    for index, parent in enumerate(parents):
        data = dict(connection_id=parent.connection_id, factory_id=default_factory.id,
                    product_line_code=None if index == 0 else "DC-DC-100", name="child")
        if kind == "erp":
            data.update(supplier_code=uuid.uuid4().hex, external_id=uuid.uuid4().hex)
        else:
            data.update(part_number=uuid.uuid4().hex, external_id=uuid.uuid4().hex)
        children.append(child_model(**data))
    db.add_all(children)
    await db.flush()
    sc = restricted_scope(admin_user, default_factory.id)
    sc.pl_scope = ProductLineScope("EXPLICIT", ["DC-DC-100"])
    visible = (await db.execute(apply_integration_scope(select(child_model), child_model, parent_model, sc))).scalars().all()
    assert children[0] in visible
    assert children[1] not in visible
    await api._check_factory_access(children[0], sc, db)
    with pytest.raises(HTTPException):
        await api._check_factory_access(children[1], sc, db)


@pytest.mark.asyncio
async def test_csr_mixed_factory_customers_rejected_without_partial_plan_write(db, admin_user, default_factory):
    from app.models.control_plan import ControlPlan
    from app.models.customer_quality import Customer
    from app.models.factory import Factory
    from app.services.control_plan_service import sync_csr_to_control_plan
    other = Factory(code="SEC-" + uuid.uuid4().hex[:12], name="other")
    db.add(other)
    await db.flush()
    plan = ControlPlan(document_no=uuid.uuid4().hex, title="plan", factory_id=default_factory.id,
                       product_line_code="DC-DC-100", customer_requirements=[{"title": "keep", "source": "manual"}])
    customers = [Customer(customer_code=uuid.uuid4().hex[:20], name="allowed", factory_id=default_factory.id, csr_list=[{"title": "allowed CSR"}]),
                 Customer(customer_code=uuid.uuid4().hex[:20], name="forbidden", factory_id=other.id, csr_list=[{"title": "secret CSR"}])]
    db.add_all([plan] + customers)
    await db.flush()
    sc = restricted_scope(admin_user, default_factory.id)
    sc.pl_scope = ProductLineScope("EXPLICIT", ["DC-DC-100"])
    with patch("app.core.permissions.get_user_permission", AsyncMock(return_value=5)):
        with pytest.raises(HTTPException) as error:
            await sync_csr_to_control_plan(db, plan.cp_id, [customer.customer_id for customer in customers], admin_user.user_id, scope=sc)
    assert error.value.status_code == 404
    await db.refresh(plan)
    assert plan.customer_requirements == [{"title": "keep", "source": "manual"}]


@pytest.mark.asyncio
async def test_authorized_control_plan_approval_reloads_items_after_scope_lock(db, admin_user, default_factory):
    from app.models.control_plan import ControlPlan, ControlPlanItem
    from app.services.control_plan_service import approve_control_plan, get_control_plan
    from app.models.control_plan_version import ControlPlanVersion
    from sqlalchemy import select
    plan = ControlPlan(document_no=uuid.uuid4().hex, title="authorized approval", product_line_code="DC-DC-100", factory_id=default_factory.id)
    db.add(plan)
    await db.flush()
    db.add(ControlPlanItem(cp_id=plan.cp_id, factory_id=default_factory.id, process_name="actual item", step_no="10"))
    await db.flush()
    plan = await get_control_plan(db, plan.cp_id)
    assert len(plan.items) == 1
    sc = restricted_scope(admin_user, default_factory.id)
    sc.pl_scope = ProductLineScope("EXPLICIT", ["DC-DC-100"])
    with patch("app.core.permissions.get_user_permission", AsyncMock(return_value=5)):
        approved = await approve_control_plan(db, plan, admin_user.user_id, scope=sc)
    assert approved.status == "approved"
    from app.schemas.control_plan import ControlPlanResponse
    assert ControlPlanResponse.model_validate(approved).items[0].process_name == "actual item"
    version = (await db.execute(select(ControlPlanVersion).where(ControlPlanVersion.cp_id == plan.cp_id))).scalar_one()
    assert version.items_snapshot[0]["process_name"] == "actual item"
