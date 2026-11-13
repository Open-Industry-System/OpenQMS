"""Pure intersection of canonical identity, plugin and task authorization."""

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


def _identity_denial(attempt: AccessAttempt) -> str | None:
    if attempt.identity_levels.get(attempt.spec.owner, PermissionLevel.NONE) < attempt.spec.required_level:
        return 'identity permission denied'
    if (attempt.identity_factories is None
            and attempt.identity_levels.get(Module.GROUP, PermissionLevel.NONE) < PermissionLevel.ADMIN):
        return 'identity factory denied'
    if attempt.identity_factories is not None and attempt.factory_id not in attempt.identity_factories:
        return 'identity factory denied'
    if attempt.identity_product_lines is None and not attempt.identity_bypass_row_level_security:
        return 'identity product line denied'
    if attempt.identity_product_lines is not None and attempt.product_line_code not in attempt.identity_product_lines:
        return 'identity product line denied'
    return None


def can_discover_source_plugin(attempt: AccessAttempt) -> bool:
    """Directory-only predicate: identity and one plugin scope, never a task grant."""
    from app.services.capa_agent_capabilities import CAPA_D4_ROOT_CAUSE_TEXT_CONTRACT
    contract = CAPA_D4_ROOT_CAUSE_TEXT_CONTRACT
    declared = get_capability(contract.capability_id, profile=attempt.catalog_profile)
    source = attempt.current_source
    return bool(declared is not None and declared == attempt.spec
        and declared.approval_floor == ApprovalFloor.DIRECT
        and _identity_denial(attempt) is None
        and _grant_covers(attempt.plugin_grant, attempt)
        and source is not None and source == attempt.plugin_source_scope
        and source.target_report_id == attempt.object_id and source.derived_projection_id == declared.id
        and source.source_projection_id == contract.source_projection_id and source.source_module == Module.FMEA)


def _intersect_scopes(attempt: AccessAttempt) -> AccessDecision:
    reason = "allowed"
    if attempt.spec.approval_floor == ApprovalFloor.DENY:
        reason = "capability disabled"
    elif (attempt.spec.kind == "context" and attempt.spec.projection not in {"masked", "raw"}
          or attempt.spec.kind == "command" and attempt.spec.projection != "none"
          or attempt.spec.kind not in {"context", "command"}):
        reason = "unknown capability contract"
    elif (identity_reason := _identity_denial(attempt)) is not None:
        reason = identity_reason
    elif not _grant_covers(attempt.plugin_grant, attempt):
        reason = "plugin grant denied"
    elif not _grant_covers(attempt.task_grant, attempt):
        reason = "task grant denied"
    elif attempt.spec.kind == "command" and attempt.task_grant.object_ids is None:
        reason = "command requires explicit task object"
    return AccessDecision(reason == "allowed", reason, attempt.spec.approval_floor)


def authorize(attempt: AccessAttempt) -> AccessDecision:
    declared = get_capability(attempt.spec.id, profile=attempt.catalog_profile)
    if declared is None:
        return AccessDecision(False, "unknown capability", ApprovalFloor.DENY)
    if declared != attempt.spec:
        return AccessDecision(False, "capability definition mismatch", declared.approval_floor)
    decision = _intersect_scopes(attempt)
    if not decision.allowed:
        return decision
    from app.services.capa_agent_capabilities import CAPA_D4_ROOT_CAUSE_TEXT_CONTRACT
    from .derived_sources import source_intersection_covers
    contract = CAPA_D4_ROOT_CAUSE_TEXT_CONTRACT
    if declared.id == contract.capability_id:
        source = attempt.current_source
        if (source is None or source.target_report_id != attempt.object_id
                or source.derived_projection_id != contract.capability_id
                or source.source_projection_id != contract.source_projection_id
                or source.source_module != Module.FMEA
                or not source_intersection_covers(source, attempt.plugin_source_scope, attempt.task_source_scope)):
            return AccessDecision(False, 'source scope denied', declared.approval_floor)
    return decision
