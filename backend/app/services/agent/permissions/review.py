"""Minimum approval route and employee reviewer eligibility."""

from collections.abc import Mapping
from uuid import UUID

from app.core.permissions import Module, PermissionLevel

from .types import ApprovalFloor, CapabilitySpec


def route_review(module_floor: ApprovalFloor, admin_floor: ApprovalFloor) -> ApprovalFloor:
    return max(module_floor, admin_floor)


def can_employee_approve(spec: CapabilitySpec, executor_id: UUID | None,
                         approver_id: UUID, approver_levels: Mapping[Module, PermissionLevel],
                         has_capability_approval: bool, in_object_scope: bool,
                         is_active: bool, is_employee: bool,
                         requester_id: UUID | None = None) -> bool:
    return (spec.approval_floor != ApprovalFloor.DENY
            and is_active and is_employee and has_capability_approval and in_object_scope
            and approver_levels.get(spec.owner, PermissionLevel.NONE) >= spec.approver_level
            and (executor_id is None or executor_id != approver_id)
            and approver_id != requester_id)
