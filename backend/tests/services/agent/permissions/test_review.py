from dataclasses import replace
from uuid import uuid4

from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions.review import can_employee_approve, route_review
from app.services.agent.permissions.types import ApprovalFloor, CapabilitySpec


def _spec(floor=ApprovalFloor.HUMAN):
    return CapabilitySpec("capa.propose.v1", Module.CAPA, "command", PermissionLevel.EDIT, floor, "none")


def test_service_executor_does_not_force_human_review_or_act_as_reviewer():
    spec = _spec(ApprovalFloor.DIRECT)
    assert route_review(spec.approval_floor, ApprovalFloor.DIRECT) == ApprovalFloor.DIRECT
    assert route_review(spec.approval_floor, ApprovalFloor.HUMAN) == ApprovalFloor.HUMAN
    employee = uuid4()
    levels = {Module.CAPA: PermissionLevel.APPROVE}
    assert can_employee_approve(spec, None, employee, levels, True, True, True, True)
    assert not can_employee_approve(spec, employee, employee, levels, True, True, True, True)
    assert not can_employee_approve(spec, None, employee, levels, True, False, True, True)
    assert not can_employee_approve(spec, None, employee, levels, True, True, False, True)
    assert not can_employee_approve(spec, None, employee, levels, True, True, True, False)


def test_dedicated_approval_and_owner_module_permission_are_both_required():
    spec = _spec()
    employee = uuid4()
    assert not can_employee_approve(spec, None, employee, {Module.FMEA: PermissionLevel.ADMIN}, True, True, True, True)
    assert not can_employee_approve(spec, None, employee, {Module.CAPA: PermissionLevel.APPROVE}, False, True, True, True)
    assert not can_employee_approve(spec, None, employee, {Module.CAPA: PermissionLevel.VIEW}, True, True, True, True)


def test_disabled_capability_cannot_be_approved_or_downgraded():
    spec = _spec(ApprovalFloor.DENY)
    assert route_review(spec.approval_floor, ApprovalFloor.DIRECT) == ApprovalFloor.DENY
    assert not can_employee_approve(spec, None, uuid4(), {Module.CAPA: PermissionLevel.ADMIN}, True, True, True, True)


def test_inactive_or_underqualified_employee_cannot_approve():
    spec = replace(_spec(), approver_level=PermissionLevel.ADMIN)
    employee = uuid4()
    levels = {Module.CAPA: PermissionLevel.APPROVE}
    assert not can_employee_approve(spec, None, employee, levels, True, True, True, True)
    assert not can_employee_approve(spec, None, employee, {Module.CAPA: PermissionLevel.ADMIN}, True, True, False, True)
    assert can_employee_approve(replace(spec, approver_level=PermissionLevel.APPROVE), None,
                                employee, levels, True, True, True, True)
