from uuid import UUID

from app.core.permissions import PermissionLevel
from app.services.agent.permissions.types import ApprovalFloor, CapabilitySpec


def route_review(module_floor: ApprovalFloor, admin_floor: ApprovalFloor) -> ApprovalFloor:
    return max(module_floor, admin_floor)


def can_employee_approve(
    spec: CapabilitySpec,
    executor_id: UUID | None,
    approver_id: UUID,
    approver_level: PermissionLevel,
    in_object_scope: bool,
    is_active: bool,
    is_employee: bool,
    requester_id: UUID | None = None,
) -> bool:
    return (
        is_active
        and is_employee
        and in_object_scope
        and approver_level >= spec.approver_level
        and approver_id != executor_id
        and approver_id != requester_id
    )
