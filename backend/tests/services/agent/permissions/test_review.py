from dataclasses import replace
from types import MappingProxyType
from uuid import uuid4

import pytest

from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions import catalog
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


@pytest.mark.parametrize("service_execution", [True, False])
def test_requester_cannot_approve_their_own_request(service_execution):
    requester = uuid4()
    executor = None if service_execution else uuid4()
    assert not can_employee_approve(
        _spec(), executor, requester, {Module.CAPA: PermissionLevel.APPROVE},
        True, True, True, True, requester_id=requester,
    )


def test_independent_employee_can_approve_service_request():
    assert can_employee_approve(
        _spec(), None, uuid4(), {Module.CAPA: PermissionLevel.APPROVE},
        True, True, True, True, requester_id=uuid4(),
    )


def test_module_minimum_cannot_be_reduced_by_admin_or_model_review():
    from app.services.agent.permissions.review import route_review

    assert route_review(ApprovalFloor.HUMAN, ApprovalFloor.DIRECT) == ApprovalFloor.HUMAN
    assert route_review(ApprovalFloor.DENY, ApprovalFloor.DIRECT) == ApprovalFloor.DENY
    assert route_review(ApprovalFloor.MODEL_REVIEW, ApprovalFloor.DIRECT) == ApprovalFloor.MODEL_REVIEW


def test_task_grant_is_separate_from_operation_review(monkeypatch):
    from datetime import UTC, datetime
    from app.services.agent.permissions.access import authorize
    from app.services.agent.permissions.review import route_review
    from app.services.agent.permissions.types import AccessAttempt, Grant

    factory, obj = uuid4(), uuid4()
    spec = CapabilitySpec(
        "capa.read.v1", Module.CAPA, "context", PermissionLevel.VIEW,
        ApprovalFloor.DIRECT, "masked",
    )
    monkeypatch.setattr(catalog, "CAPA_CAPABILITIES", MappingProxyType({spec.id: spec}))
    plugin_grant = Grant(spec.id, frozenset({factory}), frozenset({obj}), frozenset({"DC-DC-100"}))
    attempt = AccessAttempt(
        spec, {Module.CAPA: PermissionLevel.VIEW}, frozenset({factory}), frozenset({"DC-DC-100"}),
        plugin_grant, None, factory, obj, "DC-DC-100", datetime.now(UTC),
    )
    assert route_review(spec.approval_floor, ApprovalFloor.DIRECT) == ApprovalFloor.DIRECT
    assert authorize(replace(attempt, task_grant=plugin_grant)).allowed
    assert not authorize(attempt).allowed
