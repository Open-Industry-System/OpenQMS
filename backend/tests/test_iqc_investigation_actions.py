from dataclasses import replace
from uuid import uuid4

import pytest

from app.core.deps import RequestScope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.core.permissions import Module, PermissionLevel
from app.models.capa import CAPAEightD
from app.models.iqc_inspection import IqcInspection
from app.models.product_line import ProductLine
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.supplier import Supplier
from app.models.user import User
from app.services.iqc_investigation_actions import (
    InvestigationAction,
    read_review_investigation_hint,
    review_investigation_hint,
    validate_investigation_action,
)
from app.services.iqc_investigation_associations import AssociationSnapshot, LinkedInvestigation


def _empty():
    return AssociationSnapshot((), "current", True, False, ("scar", "capa"))


def _linked():
    empty = _empty()
    capa = LinkedInvestigation("capa", uuid4(), "8D-123", "open", "Repair", (), (), "version")
    return replace(empty, investigations=(capa,), version="with-link")


@pytest.mark.parametrize("checked", [None, replace(_empty(), complete=False), replace(_empty(), ambiguous=True), _linked()])
def test_publication_allows_safe_check_instead_of_unconfirmed_new(checked):
    with pytest.raises(ValueError, match="complete"):
        validate_investigation_action(InvestigationAction.CONSIDER_NEW, checked)
    validate_investigation_action(InvestigationAction.CHECK_EXISTING, checked)


def test_publication_requires_safe_schema_actions():
    validate_investigation_action(InvestigationAction.CONSIDER_NEW, _empty())
    validate_investigation_action(InvestigationAction.SUPPLEMENT_EXISTING, _linked())
    with pytest.raises(ValueError, match="unambiguous"):
        validate_investigation_action(InvestigationAction.SUPPLEMENT_EXISTING, _empty())
    with pytest.raises(ValueError, match="Invalid"):
        validate_investigation_action("consider_new", _empty())


def test_review_on_missing_incomplete_ambiguous_or_stale_lookup():
    original = InvestigationAction.CONSIDER_NEW
    for checked in (None, replace(_empty(), complete=False), replace(_linked(), ambiguous=True)):
        assert review_investigation_hint(original, is_current=True, visible=checked).action is InvestigationAction.CHECK_EXISTING
    assert review_investigation_hint(original, is_current=False, visible=_empty()).action is InvestigationAction.CHECK_EXISTING
    newer = review_investigation_hint(original, is_current=False, visible=_linked())
    assert newer.action is InvestigationAction.SUPPLEMENT_EXISTING


@pytest.mark.asyncio
async def test_shared_result_gets_separate_hints_for_the_current_employee(db, request_scope_all, default_factory):
    """Use the same recorded action with two real database-backed employee scopes."""
    line = "DC-DC-100"
    second_line = f"IQC-X-{uuid4().hex[:8]}"
    role = RoleDefinition(
        id=uuid4(), role_key=f"iqc-reader-{uuid4().hex[:8]}",
        name_en="IQC reader", name_zh="IQC 读者", is_active=True,
    )
    factory_id = default_factory.id
    db.add_all([role, ProductLine(code=second_line, name=second_line, factory_id=factory_id)])
    await db.flush()

    employee_b = User(
        user_id=uuid4(), username=f"test_iqc_reader_{uuid4().hex[:8]}",
        display_name="Reader B", password_hash="hashed", role_id=role.id,
        legacy_role="viewer", is_active=True, factory_id=factory_id,
    )
    db.add(employee_b)
    db.add_all(RolePermission(role_id=role.id, module=module, permission_level=PermissionLevel.VIEW)
               for module in (Module.IQC, Module.SCAR, Module.CAPA))
    await db.flush()
    db.add(UserProductLine(user_id=employee_b.user_id, product_line_code=line))

    supplier = Supplier(
        supplier_id=uuid4(), supplier_no=f"SUP-{uuid4().hex[:8]}",
        factory_id=factory_id, name="Example Supplier", short_name="Example",
        created_by=request_scope_all.user.user_id,
    )
    report = CAPAEightD(
        report_id=uuid4(), document_no=f"8D-{uuid4().hex[:8]}", title="Existing investigation",
        factory_id=factory_id, product_line_code=second_line,
    )
    db.add_all([supplier, report])
    await db.flush()
    inspection = IqcInspection(
        inspection_id=uuid4(), inspection_no=f"IQC-{uuid4().hex[:8]}",
        supplier_id=supplier.supplier_id, factory_id=factory_id,
        product_line_code=line, inspection_result="rejected",
    )
    db.add(inspection)
    await db.flush()

    scope_b = RequestScope(
        factory_scope=FactoryScope([factory_id], factory_id),
        effective_factory_id=factory_id,
        pl_scope=ProductLineScope("EXPLICIT", [line]), user=employee_b,
    )
    # Source admission and result persistence belong to the result read path.
    recorded = InvestigationAction.CONSIDER_NEW
    result = dict(recorded=recorded, is_current=True, inspection_ids=(inspection.inspection_id,),
                  factory_id=factory_id)
    before_b = await read_review_investigation_hint(db, scope_b, **result)

    inspection.linked_capa_id = report.report_id
    await db.flush()
    hint_a = await read_review_investigation_hint(db, request_scope_all, **result)
    hint_b = await read_review_investigation_hint(db, scope_b, **result)

    assert before_b == hint_b
    assert hint_b.action is InvestigationAction.CONSIDER_NEW
    assert not hint_b.investigations
    assert hint_a.action is InvestigationAction.SUPPLEMENT_EXISTING
    assert [(entry.object_id, entry.href) for entry in hint_a.investigations] == [
        (report.report_id, f"/capa/{report.report_id}"),
    ]
    assert result["recorded"] is recorded
    assert not db.new and not db.dirty
