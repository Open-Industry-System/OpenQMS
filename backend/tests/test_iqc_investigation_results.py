import json
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.deps import RequestScope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.core.permissions import Module, PermissionLevel
from app.models.agent_iqc_investigation import IqcInvestigationBinding, IqcInvestigationReceipt
from app.models.agent_plugin import AgentPluginInstallation
from app.models.agent_runtime_event import AgentResult
from app.models.agent_task import AgentRun, AgentTask
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.iqc_inspection_item import IqcInspectionItem, IqcItemMeasurement
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.supplier import SupplierSCAR
from app.models.user import User
from app.services.agent_runtime import iqc_investigation_results as service, iqc_investigation_tasks as tasks
from app.services.iqc_investigation_actions import InvestigationAction
from app.services import iqc_investigation_associations
from app.services.iqc_investigation_associations import read_linked_investigations
from app.services.iqc_investigation_facts import read_inspection_facts, read_item_page
from app.services.iqc_investigation_optional import SUPPLIER_PROJECTION, read_current_supplier
from tests.test_iqc_investigation_optional import sources  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.requires_db]


@pytest_asyncio.fixture
async def active_iqc(db, sources, monkeypatch, request):
    inspection, initiator, *_ = sources
    inspection.judged_at = datetime.now(UTC)
    options = getattr(request, "param", {})
    inspection.lot_no = options.get("lot_no", "LOT-123")
    inspection.defect_description = options.get("defect_description", "外观划痕")
    if options.get("inverted_limits"):
        inspection.inspection_mode = "detailed"
        item = IqcInspectionItem(
            inspection_id=inspection.inspection_id, factory_id=inspection.factory_id,
            category="dimension", item_name="外径", inspect_type="variable",
            spec_lower=12, spec_upper=10, result="rejected",
        )
        db.add(item)
        await db.flush()
        db.add(IqcItemMeasurement(item_id=item.item_id, factory_id=inspection.factory_id, measured_value=11))
    await db.flush()
    facts = await read_inspection_facts(db, initiator, inspection.inspection_id)
    plugin = AgentPluginInstallation(
        installation_id=uuid4(), plugin_key="iqc-publish-test", plugin_version="1",
        manifest={}, secret_hash="unused", created_by=initiator.user.user_id,
    )
    db.add(plugin)
    await db.flush()
    task = AgentTask(
        task_id=uuid4(), initiator_id=initiator.user.user_id, executor_user_id=initiator.user.user_id,
        preferred_installation_id=plugin.installation_id, request_key="iqc-publish",
        status="ready", task_type=tasks.TASK_TYPE, factory_id=inspection.factory_id,
        target_iqc_inspection_id=inspection.inspection_id,
    )
    db.add(task)
    await db.flush()
    run = AgentRun(
        run_id=uuid4(), task_id=task.task_id, installation_id=plugin.installation_id,
        plugin_version=plugin.plugin_version, status="active", lease_epoch=3,
        claim_key="test-claim", lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )

    # Use the ordinary PostgreSQL fixture for lifecycle and ACL assertions. The
    # tenant coordinates supplied here replace only tenant namespace resolution.
    namespace = SimpleNamespace(tenant_id=uuid4(), generation=1, schema_name="public")
    monkeypatch.setattr(tasks, "namespace", lambda db: namespace)
    data = {
        "inspection_id": str(inspection.inspection_id), "factory_id": str(inspection.factory_id),
        "product_line_code": inspection.product_line_code, "facts_version": facts.version,
        "identity_generation": facts.payload["identity_generation"],
        "installation_id": str(plugin.installation_id), "allow_unassigned_line": False,
        "tenant_id": str(namespace.tenant_id), "tenant_generation": namespace.generation,
    }
    bind = IqcInvestigationBinding(task_id=task.task_id, binding=data, binding_digest=tasks._stamp(task, data))
    db.add_all([run, bind])
    await db.flush()
    context = await _receipt(
        db, task, run, service.CONTEXT, facts.version, facts.payload,
        {"members": [asdict(member) for member in facts.members]},
    )
    return inspection, initiator, facts, task, run, context


async def _receipt(db, task, run, projection, version, data, params):
    row = IqcInvestigationReceipt(
        receipt_id=uuid4(), task_id=task.task_id, run_id=run.run_id, lease_epoch=run.lease_epoch,
        kind="source", payload=json.loads(json.dumps({
            "projection": projection, "version": version, "data": data, "params": params,
        }, default=str)),
    )
    db.add(row)
    await db.flush()
    return row


async def _association(db, active_iqc):
    inspection, initiator, facts, task, run, _ = active_iqc
    line = inspection.product_line_code
    actual = await read_linked_investigations(
        db, initiator, facts.family_ids, factory_id=inspection.factory_id,
        allowed_product_lines=frozenset({line}),
    )
    return await _receipt(
        db, task, run, service.ASSOCIATIONS, actual.version, asdict(actual), {"product_lines": [line]},
    )


async def _publish(db, case, card, *, operation_key="test-publish"):
    _, initiator, _, task, run, _ = case
    return await service.publish_iqc_investigation_result(
        db, initiator, task.task_id, run.run_id, 3, operation_key=operation_key, card=card,
    )


async def _employee(db, inspection, *, module_access=(Module.IQC, Module.SCAR, Module.CAPA)):
    line = inspection.product_line_code
    factory_id = inspection.factory_id
    role = RoleDefinition(
        id=uuid4(), role_key=f"iqc-result-{uuid4().hex[:8]}",
        name_en="IQC result employee", name_zh="IQC 建议读者", is_active=True,
    )
    db.add(role)
    await db.flush()
    employee = User(
        user_id=uuid4(), username=f"iqc_result_user_{uuid4().hex[:8]}",
        display_name="IQC Result Employee", password_hash="hashed", role_id=role.id,
        legacy_role="viewer", is_active=True, factory_id=factory_id,
    )
    db.add(employee)
    db.add_all(RolePermission(role_id=role.id, module=module, permission_level=PermissionLevel.VIEW)
               for module in module_access)
    await db.flush()
    db.add(UserProductLine(user_id=employee.user_id, product_line_code=line))
    await db.flush()
    return RequestScope(FactoryScope([factory_id], factory_id), factory_id, ProductLineScope("EXPLICIT", [line]), employee)


async def test_result_requires_confirmed_association_check_then_publishes_once(db, active_iqc):
    _, _, _, task, run, context = active_iqc
    card = service.IqcResultCard(action=InvestigationAction.CONSIDER_NEW, evidence_refs=(context.receipt_id,))
    with pytest.raises(ValueError, match="association reference"):
        await _publish(db, active_iqc, card)
    assert task.status == "ready" and run.status == "active"
    assert not await db.scalar(select(func.count()).select_from(AgentResult).where(AgentResult.task_id == task.task_id))

    association = await _association(db, active_iqc)
    card = card.model_copy(update={"evidence_refs": (context.receipt_id, association.receipt_id)})
    result_id = await _publish(db, active_iqc, card)
    assert task.status == run.status == "completed" and run.lease_epoch == 4
    assert await _publish(db, active_iqc, card) == result_id
    with pytest.raises(ValueError, match="already used"):
        await _publish(db, active_iqc, card, operation_key="second-key")
    result = await db.get(AgentResult, result_id)
    assert result.payload["action"] == "consider_new"
    assert "抽样量未记录" in result.payload["card"]["d2"]
    assert "整批实际不合格数量及原因尚待核实" in result.payload["card"]["d2"]
    assert await db.scalar(select(func.count()).select_from(AuditLog).where(
        AuditLog.record_id == result_id, AuditLog.action == "COMPLETE_AGENT_IQC_INVESTIGATION",
    )) == 1


@pytest.mark.parametrize("active_iqc", [{"lot_no": None, "defect_description": None}], indirect=True)
async def test_rejection_without_batch_or_observation_publishes_card_without_d2(db, active_iqc):
    _, initiator, _, task, _, context = active_iqc
    result_id = await _publish(db, active_iqc, service.IqcResultCard(
        action=InvestigationAction.CHECK_EXISTING, evidence_refs=(context.receipt_id,), include_d2=True,
    ))
    result = await service.get_iqc_investigation_result(db, initiator, task.task_id, result_id)
    assert result["card"]["facts"]["inspection_result"] == "rejected"
    assert {"missing_batch", "missing_observation"} <= set(result["card"]["missing"])
    assert result["card"]["d2"] is None
    assert result["current_hint"]["action"] == "check_existing"


@pytest.mark.parametrize("active_iqc", [{"defect_description": None, "inverted_limits": True}], indirect=True)
async def test_inverted_measurement_limits_are_not_used_as_d2_evidence(db, active_iqc):
    inspection, initiator, facts, task, run, context = active_iqc
    item_id = await db.scalar(select(IqcInspectionItem.item_id).where(
        IqcInspectionItem.inspection_id == inspection.inspection_id,
    ))
    references = [context.receipt_id]
    for selected_item in (None, item_id):
        page = await read_item_page(db, facts, inspection.inspection_id, item_id=selected_item)
        data = service._snapshot_wire(page)
        receipt = await _receipt(db, task, run, service.ITEMS, service._digest(data), data, {
            "inspection_id": inspection.inspection_id, "item_id": selected_item, "offset": 0, "limit": 40,
        })
        references.append(receipt.receipt_id)
    result_id = await _publish(db, active_iqc, service.IqcResultCard(
        action=InvestigationAction.CHECK_EXISTING, evidence_refs=tuple(references), include_d2=True,
    ))
    result = await service.get_iqc_investigation_result(db, initiator, task.task_id, result_id)
    assert result["card"]["facts"]["inspection_result"] == "rejected"
    assert "measurement_limits_conflict" in result["card"]["missing"]
    assert result["card"]["d2"] is None
    assert any(
        row.get("measured_value") == 11
        for source in result["card"]["evidence"]
        for row in source["data"].get("rows", ())
    )


async def test_two_employees_open_the_same_saved_result_with_different_hints(db, active_iqc):
    inspection, initiator, _, task, _, context = active_iqc
    scope_b = await _employee(db, inspection)
    association = await _association(db, active_iqc)
    result_id = await _publish(db, active_iqc, service.IqcResultCard(
        action=InvestigationAction.CONSIDER_NEW, evidence_refs=(context.receipt_id, association.receipt_id),
    ))
    before_b = await service.get_iqc_investigation_result(db, scope_b, task.task_id, result_id)
    assert before_b["current_hint"]["action"] == "consider_new"

    hidden = CAPAEightD(
        report_id=uuid4(), document_no="IQC-HIDDEN-8D", title="Private existing investigation",
        factory_id=inspection.factory_id, product_line_code="IQC-HIDDEN",
    )
    db.add(hidden)
    await db.flush()
    inspection.linked_capa_id = hidden.report_id
    await db.flush()

    current_a = await service.get_iqc_investigation_result(
        db, replace(initiator, pl_scope=ProductLineScope("ALL", None)), task.task_id, result_id,
    )
    after_b = await service.get_iqc_investigation_result(db, scope_b, task.task_id, result_id)
    assert before_b == after_b
    assert current_a["result_id"] == after_b["result_id"] == str(result_id)
    assert current_a["card"] == after_b["card"]
    assert current_a["current_hint"]["action"] == "supplement_existing"
    assert [entry["href"] for entry in current_a["current_hint"]["investigations"]] == [f"/capa/{hidden.report_id}"]
    assert str(hidden.report_id) not in json.dumps(after_b)


async def test_shared_original_query_is_not_superseded_by_a_wider_reader_on_same_line(
    db, active_iqc, monkeypatch,
):
    inspection, initiator, _, task, _, context = active_iqc
    colleague = await _employee(db, inspection)
    author_id = initiator.user.user_id
    existing = CAPAEightD(
        report_id=uuid4(), document_no="IQC-SAME-LINE-8D", title="Existing investigation",
        factory_id=inspection.factory_id, product_line_code=inspection.product_line_code,
    )
    db.add(existing)
    await db.flush()
    inspection.linked_capa_id = existing.report_id
    await db.flush()
    authorize_root = iqc_investigation_associations.authorize_root

    async def authorize_inherited_source(db, user_id, report_id):
        if user_id == author_id and report_id == existing.report_id:
            raise PermissionError("Inherited CAPA source unavailable")
        return await authorize_root(db, user_id, report_id)

    # Vary inherited CAPA-source admission, while using real scoped graph reads,
    # saved evidence, and the same result primary key for both authenticated users.
    monkeypatch.setattr(iqc_investigation_associations, "authorize_root", authorize_inherited_source)
    association = await _association(db, active_iqc)
    result_id = await _publish(db, active_iqc, service.IqcResultCard(
        action=InvestigationAction.CONSIDER_NEW, evidence_refs=(context.receipt_id, association.receipt_id),
    ))
    expanded = await service.get_iqc_investigation_result(db, colleague, task.task_id, result_id)
    original = await service.get_iqc_investigation_result(db, initiator, task.task_id, result_id)
    assert not expanded["stale"] and not original["stale"]
    assert expanded["card"] == original["card"]
    assert expanded["current_hint"]["action"] == "supplement_existing"
    assert original["current_hint"]["action"] == "consider_new"
    assert str(existing.report_id) not in json.dumps(original)


@pytest.mark.parametrize("hidden_from_author", [False, True])
async def test_shared_scar_version_ignores_a_link_only_one_employee_can_read(
    db, active_iqc, monkeypatch, hidden_from_author,
):
    inspection, initiator, _, task, _, context = active_iqc
    colleague = await _employee(db, inspection)
    scar = SupplierSCAR(
        scar_id=uuid4(), scar_no="SCAR-IQC-SHARED", supplier_id=inspection.supplier_id,
        factory_id=inspection.factory_id, product_line_code=inspection.product_line_code,
        source_type="iqc", source_id=inspection.inspection_id, description="Recorded correction",
    )
    db.add(scar)
    await db.flush()
    association = await _association(db, active_iqc)
    result_id = await _publish(db, active_iqc, service.IqcResultCard(
        action=InvestigationAction.SUPPLEMENT_EXISTING, evidence_refs=(context.receipt_id, association.receipt_id),
    ))
    before = await service.get_iqc_investigation_result(db, colleague, task.task_id, result_id)
    assert not before["stale"]
    assert [entry["object_id"] for entry in before["current_hint"]["investigations"]] == [str(scar.scar_id)]

    hidden = CAPAEightD(
        report_id=uuid4(), document_no="8D-IQC-SHARED-EDGE", title="Restricted inherited sources",
        factory_id=inspection.factory_id, product_line_code=inspection.product_line_code,
        scar_ref_id=scar.scar_id,
    )
    authorize_root = iqc_investigation_associations.authorize_root
    restricted_user = initiator.user if hidden_from_author else colleague.user

    async def authorize_inherited_source(db, user_id, report_id):
        if user_id == restricted_user.user_id and report_id == hidden.report_id:
            raise PermissionError("Inherited CAPA source unavailable")
        return await authorize_root(db, user_id, report_id)

    monkeypatch.setattr(iqc_investigation_associations, "authorize_root", authorize_inherited_source)
    db.add(hidden)
    await db.flush()

    author_view = await service.get_iqc_investigation_result(db, initiator, task.task_id, result_id)
    colleague_view = await service.get_iqc_investigation_result(db, colleague, task.task_id, result_id)
    assert author_view["stale"] is (not hidden_from_author)
    assert not colleague_view["stale"]
    assert author_view["card"] == colleague_view["card"] == before["card"]
    if hidden_from_author:
        assert str(hidden.report_id) in json.dumps(colleague_view["current_hint"])
        assert str(hidden.report_id) not in json.dumps(author_view)
    else:
        assert str(hidden.report_id) in json.dumps(author_view["current_hint"])
        assert colleague_view == before

    author_permission = await db.scalar(select(RolePermission).where(
        RolePermission.role_id == initiator.user.role_id, RolePermission.module == Module.SCAR,
    ))
    author_permission.permission_level = PermissionLevel.NONE
    await db.flush()
    unchanged = await service.get_iqc_investigation_result(db, colleague, task.task_id, result_id)
    assert unchanged == colleague_view

    scar.description = "Correction still in the reviewer's scope"
    await db.flush()
    updated_colleague = await service.get_iqc_investigation_result(db, colleague, task.task_id, result_id)
    assert updated_colleague["stale"]


async def test_optional_evidence_is_inherited_even_if_not_cited_by_the_model(db, active_iqc):
    inspection, initiator, _, task, run, context = active_iqc
    supplier = await read_current_supplier(db, initiator, inspection.inspection_id)
    await _receipt(db, task, run, SUPPLIER_PROJECTION, supplier.source.version, asdict(supplier), {})
    result_id = await _publish(db, active_iqc, service.IqcResultCard(
        action=InvestigationAction.CHECK_EXISTING, evidence_refs=(context.receipt_id,),
    ))
    unauthorized = await _employee(db, inspection)
    with pytest.raises(LookupError, match="unavailable"):
        await service.get_iqc_investigation_result(db, unauthorized, task.task_id, result_id)
    assert (await service.get_iqc_investigation_result(db, initiator, task.task_id, result_id))["result_id"] == str(result_id)


async def test_structured_action_rejects_all_worker_prose():
    fields = {"action": "check_existing", "evidence_refs": [str(uuid4())]}
    for field in ("facts", "body", "d2", "note", "investigations"):
        with pytest.raises(ValidationError, match="Extra inputs"):
            service.IqcResultCard.model_validate({**fields, field: "untrusted"})
    with pytest.raises(ValidationError):
        service.IqcResultCard.model_validate({**fields, "next_steps": ["create a new 8D"]})
