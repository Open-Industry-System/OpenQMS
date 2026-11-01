"""Pure intersection of current identity, plugin and task authorization."""

from app.core.permissions import Module, PermissionLevel

from .catalog import get_capability

from .types import AccessAttempt, AccessDecision, ApprovalFloor, Grant


def _grant_covers(grant: Grant | None, attempt: AccessAttempt) -> bool:
    if grant is None or grant.capability_id != attempt.spec.id:
        return False
    if grant.expires_at is not None:
        if grant.expires_at.tzinfo is None or attempt.now.tzinfo is None:
            return False
        if grant.expires_at <= attempt.now:
            return False
    return (attempt.factory_id in grant.factory_ids
            and (grant.object_ids is None or attempt.object_id in grant.object_ids)
            and (grant.product_line_codes is None or attempt.product_line_code in grant.product_line_codes))


def _intersect_scopes(attempt: AccessAttempt) -> AccessDecision:
    reason = "allowed"
    if attempt.spec.approval_floor == ApprovalFloor.DENY:
        reason = "capability disabled"
    elif (attempt.spec.kind == "context" and attempt.spec.projection not in {"masked", "raw"}
          or attempt.spec.kind == "command" and attempt.spec.projection != "none"
          or attempt.spec.kind not in {"context", "command"}):
        reason = "unknown capability contract"
    elif attempt.identity_levels.get(attempt.spec.owner, PermissionLevel.NONE) < attempt.spec.required_level:
        reason = "identity permission denied"
    elif (attempt.identity_factories is None
          and attempt.identity_levels.get(Module.GROUP, PermissionLevel.NONE) < PermissionLevel.ADMIN):
        reason = "identity factory denied"
    elif attempt.identity_factories is not None and attempt.factory_id not in attempt.identity_factories:
        reason = "identity factory denied"
    elif attempt.identity_product_lines is None and not attempt.identity_bypass_row_level_security:
        reason = "identity product line denied"
    elif attempt.identity_product_lines is not None and attempt.product_line_code not in attempt.identity_product_lines:
        reason = "identity product line denied"
    elif not _grant_covers(attempt.plugin_grant, attempt):
        reason = "plugin grant denied"
    elif not _grant_covers(attempt.task_grant, attempt):
        reason = "task grant denied"
    elif attempt.spec.kind == "command" and attempt.task_grant.object_ids is None:
        reason = "command requires explicit task object"
    return AccessDecision(reason == "allowed", reason, attempt.spec.approval_floor)


def authorize(attempt: AccessAttempt) -> AccessDecision:
    canonical = get_capability(attempt.spec.id)
    if canonical is None or canonical != attempt.spec:
        return AccessDecision(False, "unlisted capability", ApprovalFloor.DENY)
    return _intersect_scopes(attempt)
