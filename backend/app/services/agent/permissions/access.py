from app.core.permissions import PermissionLevel

from app.services.agent.permissions.catalog import get_capability
from app.services.agent.permissions.types import AccessAttempt, AccessDecision, ApprovalFloor, Grant


def _grant_covers(grant: Grant | None, attempt: AccessAttempt) -> bool:
    if grant is None or grant.capability_id != attempt.spec.id:
        return False
    if grant.expires_at is not None:
        if grant.expires_at.tzinfo is None or attempt.now.tzinfo is None:
            return False
        if grant.expires_at <= attempt.now:
            return False
    return (
        attempt.factory_id in grant.factory_ids
        and (grant.object_ids is None or attempt.object_id in grant.object_ids)
        and (grant.product_line_codes is None or attempt.product_line_code in grant.product_line_codes)
    )


def authorize(attempt: AccessAttempt) -> AccessDecision:
    declared = get_capability(attempt.spec.id)
    if declared is None:
        return AccessDecision(False, "unknown capability", ApprovalFloor.DENY)
    if declared != attempt.spec:
        return AccessDecision(False, "capability definition mismatch", declared.approval_floor)

    reason = "allowed"
    if attempt.spec.kind not in {"context", "command"}:
        reason = "unknown capability kind"
    elif attempt.spec.approval_floor == ApprovalFloor.DENY:
        reason = "capability disabled"
    elif attempt.identity_levels.get(attempt.spec.owner, PermissionLevel.NONE) < attempt.spec.required_level:
        reason = "identity permission denied"
    elif attempt.identity_factories is not None and attempt.factory_id not in attempt.identity_factories:
        reason = "identity factory denied"
    elif attempt.identity_product_lines is not None and attempt.product_line_code not in attempt.identity_product_lines:
        reason = "identity product line denied"
    elif not _grant_covers(attempt.plugin_grant, attempt):
        reason = "plugin grant denied"
    elif not _grant_covers(attempt.task_grant, attempt):
        reason = "task grant denied"
    elif attempt.spec.kind == "command" and attempt.task_grant.object_ids is None:
        reason = "command requires explicit task object"
    return AccessDecision(reason == "allowed", reason, attempt.spec.approval_floor)
