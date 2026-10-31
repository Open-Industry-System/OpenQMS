from uuid import uuid4

from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions.types import ApprovalFloor, CapabilitySpec


def test_service_executor_does_not_force_human_review_or_act_as_reviewer():
    from app.services.agent.permissions.review import can_employee_approve, route_review

    spec = CapabilitySpec(
        "capa.propose.v1", Module.CAPA, "command", PermissionLevel.EDIT,
        ApprovalFloor.DIRECT, "none",
    )
    assert route_review(spec.approval_floor, ApprovalFloor.DIRECT) == ApprovalFloor.DIRECT
    assert route_review(spec.approval_floor, ApprovalFloor.HUMAN) == ApprovalFloor.HUMAN
    employee = uuid4()
    assert can_employee_approve(spec, None, employee, PermissionLevel.APPROVE, True, True, True)
    assert not can_employee_approve(spec, employee, employee, PermissionLevel.APPROVE, True, True, True)
    assert not can_employee_approve(spec, None, employee, PermissionLevel.VIEW, True, True, True)
    assert not can_employee_approve(spec, None, employee, PermissionLevel.APPROVE, False, True, True)
    assert not can_employee_approve(spec, None, employee, PermissionLevel.APPROVE, True, False, True)
    assert not can_employee_approve(spec, None, employee, PermissionLevel.APPROVE, True, True, False)
    assert not can_employee_approve(
        spec, None, employee, PermissionLevel.APPROVE, True, True, True,
        requester_id=employee,
    )


def test_module_minimum_cannot_be_reduced_by_admin_or_model_review():
    from app.services.agent.permissions.review import route_review

    assert route_review(ApprovalFloor.HUMAN, ApprovalFloor.DIRECT) == ApprovalFloor.HUMAN
    assert route_review(ApprovalFloor.DENY, ApprovalFloor.DIRECT) == ApprovalFloor.DENY
    assert route_review(ApprovalFloor.MODEL_REVIEW, ApprovalFloor.DIRECT) == ApprovalFloor.MODEL_REVIEW


def test_task_grant_is_separate_from_operation_review():
    from datetime import UTC, datetime
    from app.services.agent.permissions.access import authorize
    from app.services.agent.permissions.review import route_review
    from app.services.agent.permissions.types import AccessAttempt, Grant

    factory, obj = uuid4(), uuid4()
    spec = CapabilitySpec(
        "capa.read.v1", Module.CAPA, "context", PermissionLevel.VIEW,
        ApprovalFloor.DIRECT, "masked",
    )
    plugin_grant = Grant(spec.id, frozenset({factory}), frozenset({obj}), None)
    attempt = AccessAttempt(
        spec, {Module.CAPA: PermissionLevel.VIEW}, frozenset({factory}), None,
        plugin_grant, None, factory, obj, "DC-DC-100", datetime.now(UTC),
    )
    assert route_review(spec.approval_floor, ApprovalFloor.DIRECT) == ApprovalFloor.DIRECT
    assert not authorize(attempt).allowed
