from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from uuid import UUID

from app.core.permissions import Module, PermissionLevel


class ApprovalFloor(IntEnum):
    DIRECT = 0
    MODEL_REVIEW = 1
    HUMAN = 2
    DENY = 3


@dataclass(frozen=True)
class CapabilitySpec:
    id: str
    owner: Module
    kind: str
    required_level: PermissionLevel
    approval_floor: ApprovalFloor
    projection: str
    approver_level: PermissionLevel = PermissionLevel.APPROVE
    self_approval_allowed: bool = False


@dataclass(frozen=True)
class Grant:
    capability_id: str
    factory_ids: frozenset[UUID]
    object_ids: frozenset[UUID] | None
    product_line_codes: frozenset[str] | None
    expires_at: datetime | None = None


@dataclass(frozen=True)
class AccessAttempt:
    spec: CapabilitySpec
    identity_levels: dict[Module, PermissionLevel]
    identity_factories: frozenset[UUID] | None
    identity_product_lines: frozenset[str] | None
    plugin_grant: Grant | None
    task_grant: Grant | None
    factory_id: UUID
    object_id: UUID
    product_line_code: str
    now: datetime


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str
    approval_floor: ApprovalFloor
